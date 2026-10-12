"""APScheduler background worker (§4): periodic scrape → match → coupon → alert."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from . import config, database
from .scrapers import base as scrape_base
from .scrapers.base import classify_scope
from .scrapers import slickdeals, retailers, aggregators, providers
from .scrapers import coupons as coupon_mod
from .processors import matcher, unit_price, dedup

log = logging.getLogger(__name__)

def run_pipeline() -> dict:
    """One full cycle. Returns counts; safe to call from scheduler or API."""
    counts = {"found": 0, "matched": 0, "alerted": 0, "coupons": 0}
    with database.get_connection() as conn:
        watchlist = matcher.load_watchlist(conn)
        zip_code = database.get_setting(conn, "zip_code", config.ZIP_CODE) or config.ZIP_CODE
        for source, fetcher in [
            ("deal_rss", lambda: slickdeals.fetch_rss()),
            ("aggregators", aggregators.fetch_aggregators),
            ("serpapi", lambda: providers.fetch_serpapi(conn)),
            ("retailers", lambda: retailers.fetch_all_retailers(zip_code)),
        ]:
            run_id = scrape_base.start_run(conn, source)
            try:
                deals = fetcher()
                if deals is None:
                    # Provider skipped (unconfigured/throttled): leave no run row.
                    conn.execute("DELETE FROM scrape_runs WHERE id=?", (run_id,))
                    conn.commit()
                    continue
                counts["found"] += len(deals)
                matched = 0
                for d in deals:
                    disc = unit_price.compute_discount_pct(d.price, d.original_price)
                    up, unit = unit_price.compute_unit_price(d.price, d.title)
                    dh = dedup.make_deal_hash(d.title, d.store, d.url)
                    # Fulfillment scope: explicit scraper label wins,
                    # else infer from title signals (in-store/pickup vs ships).
                    scope = d.scope if d.scope != "unknown" else classify_scope(d.title)
                    if not dedup.is_known(conn, dh):
                        # Brand-new find: store only if it clears the watchlist.
                        # RSS items often lack prices: gate on keyword, treat
                        # unknown discount as pass-through.
                        effective = disc if disc is not None else 99.0
                        if matcher.match_deal(d.title, d.category, effective, watchlist, d.store) is None:
                            continue
                        dedup.upsert_deal(conn, dh, d.title, d.store, d.category, d.price,
                                          d.original_price, disc, up, unit, d.url, d.image_url, d.source,
                                          scope=scope)
                    else:
                        # Already tracked: always refresh pricing/history so
                        # improved extraction or price moves correct old rows,
                        # even when the deal no longer clears the alert gate.
                        dedup.upsert_deal(conn, dh, d.title, d.store, d.category, d.price,
                                          d.original_price, disc, up, unit, d.url, d.image_url, d.source,
                                          scope=scope)
                        effective = disc if disc is not None else 99.0
                        if matcher.match_deal(d.title, d.category, effective, watchlist, d.store) is None:
                            continue
                    coupon_mod.attach_coupons(conn, dh, d.store, d.title)
                    for sig in coupon_mod.extract_coupon_signals(d.title, d.store):
                        conn.execute(
                            """INSERT OR IGNORE INTO coupons
                               (store, code, description, promo_link, deal_hash, source)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (sig.store, sig.code, sig.description, sig.promo_link, dh, sig.source),
                        )
                        counts["coupons"] += 1
                    if conn.execute(
                        "SELECT 1 FROM coupons WHERE deal_hash=? AND is_active=1",
                        (dh,),
                    ).fetchone():
                        conn.execute(
                            "UPDATE deals SET coupon_available=1 WHERE deal_hash=?", (dh,))
                    matched += 1
                    # alert once per deal
                    if not dedup.already_alerted(conn, dh):
                        from .notifiers import telegram
                        row = conn.execute(
                            "SELECT code FROM coupons WHERE deal_hash=? AND is_active=1 LIMIT 1", (dh,)
                        ).fetchone()
                        code = row["code"] if row else None
                        if telegram.send_alert(d.title, d.store, disc, code, d.url):
                            conn.execute(
                                "INSERT OR IGNORE INTO alerts (deal_hash, message) VALUES (?, ?)",
                                (dh, d.title),
                            )
                            counts["alerted"] += 1
                conn.commit()
                counts["matched"] += matched
                scrape_base.finish_run(conn, run_id, len(deals), matched)
            except Exception as ex:  # noqa: BLE001
                conn.rollback()
                scrape_base.finish_run(conn, run_id, 0, 0, error=str(ex))

        # --- Key-gated coupon providers (Takeads list + Strackr export) ---
        for psource, pfetch in [("takeads", providers.fetch_takeads_coupons),
                                ("strackr", providers.fetch_strackr)]:
            run_id = scrape_base.start_run(conn, psource)
            try:
                found = pfetch(conn)
                if found is None:
                    conn.execute("DELETE FROM scrape_runs WHERE id=?", (run_id,))
                    conn.commit()
                    continue
                n = 0
                for c in found:
                    if not c.code and not c.promo_link:
                        continue
                    cur = conn.execute(
                        """INSERT INTO coupons (store, code, description, promo_link, source)
                           SELECT ?, ?, ?, ?, ?
                           WHERE NOT EXISTS (
                             SELECT 1 FROM coupons WHERE store=?
                             AND ifnull(code,'')=ifnull(?, '')
                             AND ifnull(promo_link,'')=ifnull(?, ''))""",
                        (c.store, c.code, c.description, c.promo_link, psource,
                         c.store, c.code, c.promo_link),
                    )
                    n += cur.rowcount
                conn.commit()
                counts["coupons"] += n
                scrape_base.finish_run(conn, run_id, len(found), n)
            except Exception as ex:  # noqa: BLE001
                conn.rollback()
                scrape_base.finish_run(conn, run_id, 0, 0, error=str(ex)[:300])

        # --- Takeads enrichment: real promo codes matched to our deal URLs ---
        try:
            urls = [r["url"] for r in conn.execute(
                "SELECT url FROM deals WHERE is_active=1 AND url LIKE 'http%' "
                "ORDER BY last_seen DESC LIMIT 20").fetchall()]
            for url, codes in providers.match_takeads_for_urls(conn, urls).items():
                dh = conn.execute(
                    "SELECT deal_hash, store FROM deals WHERE url=?", (url,)).fetchone()
                if not dh:
                    continue
                for c in codes:
                    if not c.code and not c.promo_link:
                        continue
                    conn.execute(
                        """INSERT INTO coupons (store, code, description, promo_link, deal_hash, source)
                           SELECT ?, ?, ?, ?, ?, ?
                           WHERE NOT EXISTS (
                             SELECT 1 FROM coupons WHERE deal_hash=?
                             AND ifnull(code,'')=ifnull(?, ''))""",
                        (dh["store"], c.code, c.description, c.promo_link,
                         dh["deal_hash"], "takeads", dh["deal_hash"], c.code),
                    )
                    counts["coupons"] += 1
                conn.execute("UPDATE deals SET coupon_available=1 WHERE deal_hash=?",
                             (dh["deal_hash"],))
            conn.commit()
        except Exception as ex:  # noqa: BLE001
            conn.rollback()
            log.warning("Takeads enrichment failed: %s", ex)
        # Expire deals the feeds stopped carrying (dead merchant pages):
        # anything unseen for 7 days goes inactive so links stay fresh.
        # (Rotating "newest" feeds stop re-surfacing threads within hours,
        # so the window must comfortably exceed feed rotation.)
        cur = conn.execute(
            "UPDATE deals SET is_active=0 WHERE is_active=1 "
            "AND last_seen < datetime('now','-7 days')")
        counts["pruned"] = cur.rowcount
        conn.commit()
    return counts

def start_scheduler() -> BackgroundScheduler:
    from datetime import datetime as _dt
    sched = BackgroundScheduler()
    # First run immediately in the background (server stays responsive),
    # then every SCRAPE_INTERVAL_MINUTES — so fresh data never waits.
    sched.add_job(run_pipeline, "interval", minutes=config.SCRAPE_INTERVAL_MINUTES,
                  id="pipeline", next_run_time=_dt.now())
    sched.start()
    return sched
