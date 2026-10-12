"""JSON endpoints for dashboard + external clients."""
import re
from fastapi import APIRouter, Query
from pydantic import BaseModel
from .. import config, database

router = APIRouter(prefix="/api")

@router.get("/deals")
def list_deals(category: str | None = None, store: str | None = None,
               coupon_only: bool = False, scope: str | None = None,
               limit: int = Query(50, le=200)):
    q = "SELECT * FROM deals WHERE is_active = 1"
    args: list = []
    if category:
        q += " AND category = ?"; args.append(category)
    if store:
        q += " AND store = ?"; args.append(store)
    if coupon_only:
        q += " AND coupon_available = 1"
    if scope == "local":
        q += " AND scope = 'local'"
    elif scope == "online":
        q += " AND scope != 'local'"
    q += " ORDER BY last_seen DESC LIMIT ?"; args.append(limit)
    with database.get_connection() as conn:
        return [dict(r) for r in conn.execute(q, args).fetchall()]

@router.get("/coupons")
def list_coupons(active_only: bool = True):
    q = "SELECT * FROM coupons" + (" WHERE is_active = 1" if active_only else "") + " ORDER BY discovered_at DESC LIMIT 100"
    with database.get_connection() as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]

@router.get("/stats")
def stats():
    from ..main import scheduler_status  # lazy: avoids circular import
    with database.get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM deals WHERE is_active=1").fetchone()["c"]
        by_cat = {r["category"]: r["c"] for r in conn.execute(
            "SELECT category, COUNT(*) c FROM deals WHERE is_active=1 GROUP BY category").fetchall()}
        coupon_n = conn.execute("SELECT COUNT(*) c FROM coupons WHERE is_active=1").fetchone()["c"]
        last = conn.execute(
            "SELECT source, MAX(finished_at) last_run FROM scrape_runs GROUP BY source").fetchall()
    return {"active_deals": total, "by_category": by_cat,
            "active_coupons": coupon_n, "last_runs": [dict(r) for r in last],
            "scheduler": scheduler_status()}

@router.post("/scan")
def trigger_scan():
    from ..scheduler import run_pipeline
    return run_pipeline()

class ZipUpdate(BaseModel):
    zip_code: str

@router.get("/settings")
def get_settings():
    with database.get_connection() as conn:
        return {"zip_code": database.get_setting(conn, "zip_code", config.ZIP_CODE)}

@router.post("/settings/zip")
def set_zip(body: ZipUpdate):
    z = (body.zip_code or "").strip()
    if not re.fullmatch(r"\d{5}(-\d{4})?", z):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="ZIP must be 5 digits (e.g. 63005)")
    with database.get_connection() as conn:
        database.set_setting(conn, "zip_code", z)
    return {"zip_code": z}

KEY_ALLOWLIST = {"serpapi_key", "takeads_key", "strackr_key", "strackr_base"}

class KeysUpdate(BaseModel):
    keys: dict[str, str]

@router.get("/settings/keys")
def keys_status():
    """Which provider keys are configured (values never leak)."""
    import os
    env_map = {"serpapi_key": "SERPAPI_KEY", "takeads_key": "TAKEADS_KEY",
               "strackr_key": "STRACKR_KEY", "strackr_base": "STRACKR_API_BASE"}
    with database.get_connection() as conn:
        return {k: bool(database.get_setting(conn, k, "") or os.getenv(v, ""))
                for k, v in env_map.items()}

@router.post("/settings/keys")
def save_keys(body: KeysUpdate):
    saved = []
    with database.get_connection() as conn:
        for k, v in (body.keys or {}).items():
            if k in KEY_ALLOWLIST and (v or "").strip():
                database.set_setting(conn, k, v.strip())
                saved.append(k)
    return {"saved": saved}
