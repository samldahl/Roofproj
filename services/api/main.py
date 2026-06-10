"""FastAPI: serves permits to the web app, exposes admin actions."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient

load_dotenv()

app = FastAPI(title="Roofproj API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = MongoClient(os.environ["MONGO_URI"])
db = _client[os.getenv("MONGO_DB", "roofproj")]
CITIES_DIR = Path(__file__).resolve().parents[2] / "cities"


@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


@app.get("/permits")
def list_permits(
    city: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    contractor: Optional[str] = None,
    bbox: Optional[str] = Query(None, description="minLng,minLat,maxLng,maxLat"),
    limit: int = 5000,
):
    q: dict = {}
    if city:
        q["city_id"] = city
    if contractor:
        q["contractor_name"] = {"$regex": contractor, "$options": "i"}
    if year_min or year_max:
        rng: dict = {}
        if year_min:
            rng["$gte"] = f"{year_min}-01-01"
        if year_max:
            rng["$lte"] = f"{year_max}-12-31"
        q["issue_date"] = rng
    if bbox:
        try:
            min_lng, min_lat, max_lng, max_lat = (float(x) for x in bbox.split(","))
        except ValueError:
            raise HTTPException(400, "bbox must be 4 floats")
        q["location"] = {
            "$geoWithin": {
                "$box": [[min_lng, min_lat], [max_lng, max_lat]]
            }
        }

    cursor = db.permits.find(q, {"_id": 0}).limit(limit)
    return {"permits": list(cursor)}


@app.get("/cities")
def list_cities():
    return {"cities": list(db.cities.find({}, {"_id": 0}))}


@app.post("/cities/sync")
def sync_cities_from_yaml():
    """Read cities/*.yaml into the cities collection. Idempotent."""
    count = 0
    for path in CITIES_DIR.glob("*.yaml"):
        with path.open() as f:
            cfg = yaml.safe_load(f)
        db.cities.update_one({"slug": cfg["slug"]}, {"$set": cfg}, upsert=True)
        count += 1
    return {"synced": count}


@app.get("/outreach")
def list_outreach():
    return {"requests": list(db.outreach_requests.find({}, {"_id": 0}).sort("sent_at", -1).limit(200))}


@app.post("/outreach/send/{city_slug}")
def queue_outreach(city_slug: str):
    """Enqueue a DPA send. The outreach worker picks it up."""
    if not db.cities.find_one({"slug": city_slug}):
        raise HTTPException(404, "unknown city")
    db.jobs.insert_one({
        "type": "outreach_send",
        "status": "queued",
        "city_slug": city_slug,
        "claim_at": None,
        "created_at": datetime.utcnow(),
    })
    return {"queued": True}


# ---------- Pipeline dashboard ----------

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/roofproj_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/intake/upload")
async def upload_file(city_slug: str = Form(...), file: UploadFile = File(...)):
    """Manual intake: VA or operator drops an XLSX/CSV for a city.
    Saved to local upload dir, source_file recorded, normalize job queued.
    """
    if not db.cities.find_one({"slug": city_slug}):
        raise HTTPException(404, "unknown city")

    suffix = Path(file.filename or "upload").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as tmp:
        sha = hashlib.sha256()
        while chunk := await file.read(1 << 20):
            tmp.write(chunk)
            sha.update(chunk)
        local_path = Path(tmp.name)

    digest = sha.hexdigest()
    s3_key = f"raw/{city_slug}/manual/{digest[:12]}_{file.filename}"
    final_path = UPLOAD_DIR / s3_key.replace("/", "__")
    shutil.move(str(local_path), final_path)

    db.source_files.update_one(
        {"sha256": digest},
        {"$setOnInsert": {
            "city_id": city_slug,
            "s3_key": s3_key,
            "local_path": str(final_path),
            "sha256": digest,
            "filename": file.filename,
            "source": "manual_upload",
            "received_at": datetime.utcnow(),
            "processed_at": None,
        }},
        upsert=True,
    )
    db.jobs.insert_one({
        "type": "normalize",
        "status": "queued",
        "city_slug": city_slug,
        "s3_key": s3_key,
        "local_path": str(final_path),
        "claim_at": None,
        "created_at": datetime.utcnow(),
    })
    return {"ok": True, "sha256": digest, "s3_key": s3_key}


@app.get("/pipeline/stats")
def pipeline_stats():
    """Funnel snapshot: intake -> processing -> output."""
    now = datetime.utcnow()
    last_7d = now - timedelta(days=7)

    # INTAKE
    intake_by_source = list(db.source_files.aggregate([
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    ]))
    intake_7d = db.source_files.count_documents({"received_at": {"$gte": last_7d}})

    # OUTREACH (one form of intake activity)
    outreach_by_status = list(db.outreach_requests.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]))
    overdue_followups = db.outreach_requests.count_documents({
        "status": "sent", "follow_up_at": {"$lt": now}
    })

    # PROCESSING
    jobs_by_status = list(db.jobs.aggregate([
        {"$group": {"_id": {"type": "$type", "status": "$status"}, "count": {"$sum": 1}}},
    ]))
    failed_recent = list(db.jobs.find(
        {"status": "failed", "finished_at": {"$gte": last_7d}},
        {"_id": 0, "type": 1, "city_slug": 1, "error": 1, "finished_at": 1},
    ).sort("finished_at", -1).limit(10))

    # OUTPUT
    total_permits = db.permits.count_documents({})
    geocoded_permits = db.permits.count_documents({"location": {"$ne": None}})
    permits_by_city = list(db.permits.aggregate([
        {"$group": {"_id": "$city_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    permits_by_year = list(db.permits.aggregate([
        {"$group": {"_id": {"$substr": ["$issue_date", 0, 4]}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]))

    return {
        "intake": {
            "by_source": intake_by_source,
            "files_last_7d": intake_7d,
            "outreach_by_status": outreach_by_status,
            "overdue_followups": overdue_followups,
        },
        "processing": {
            "jobs_by_status": jobs_by_status,
            "recent_failures": failed_recent,
        },
        "output": {
            "total_permits": total_permits,
            "geocoded_permits": geocoded_permits,
            "geocoded_pct": round(100 * geocoded_permits / total_permits, 1) if total_permits else 0,
            "by_city": permits_by_city,
            "by_year": permits_by_year,
        },
    }


@app.get("/stats/coverage")
def coverage_stats():
    """Out of all cities we're targeting, how many have data and how good is it."""
    cities = list(db.cities.find({}, {"_id": 0, "slug": 1, "data_starts_at": 1}))
    total_cities = len(cities)

    cities_with_data = db.permits.distinct("city_id")
    cities_with_files = db.source_files.distinct("city_id")

    total_permits = db.permits.count_documents({})
    geocoded = db.permits.count_documents({"location": {"$ne": None}})

    # Per-city quality
    per_city = []
    for c in cities:
        slug = c["slug"]
        permits = db.permits.count_documents({"city_id": slug})
        geo = db.permits.count_documents({"city_id": slug, "location": {"$ne": None}})
        rejects = db.rejected_rows.count_documents({"city_id": slug})
        per_city.append({
            "slug": slug,
            "permits": permits,
            "geocoded": geo,
            "geocoded_pct": round(100 * geo / permits, 1) if permits else 0,
            "rejects": rejects,
            "reject_rate": round(100 * rejects / (rejects + permits), 1) if (rejects + permits) else 0,
            "data_starts_at": c.get("data_starts_at"),
        })

    return {
        "total_cities": total_cities,
        "cities_with_files": len(cities_with_files),
        "cities_with_data": len(cities_with_data),
        "coverage_pct": round(100 * len(cities_with_data) / total_cities, 1) if total_cities else 0,
        "total_permits": total_permits,
        "geocoded_permits": geocoded,
        "map_accuracy_pct": round(100 * geocoded / total_permits, 1) if total_permits else 0,
        "per_city": per_city,
    }


@app.get("/stats/vendors")
def vendor_stats():
    """Vendor concentration: which platforms cover the most cities?
    Used to prioritize scraper-adapter investment.
    """
    pipeline = [
        {"$group": {
            "_id": {"vendor": "$vendor", "strategy": "$strategy"},
            "cities": {"$push": "$slug"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    raw = list(db.cities.aggregate(pipeline))
    # Roll up by vendor
    by_vendor: dict = {}
    for row in raw:
        vendor = row["_id"].get("vendor") or "unknown"
        v = by_vendor.setdefault(vendor, {"vendor": vendor, "total": 0, "by_strategy": {}, "cities": []})
        v["total"] += row["count"]
        v["by_strategy"][row["_id"].get("strategy") or "?"] = row["count"]
        v["cities"].extend(row["cities"])
    out = sorted(by_vendor.values(), key=lambda v: v["total"], reverse=True)
    return {"vendors": out}


CANONICAL_FIELDS = [
    "ignore",
    "permit_number",
    "address_raw",
    "issue_date",
    "completion_date",
    "contractor_name",
    "contractor_license",
    "valuation",
    "status",
    "work_type",
    "parcel_id",
]


@app.get("/cities/{slug}/inspect")
def inspect_city_file(slug: str, header_row: int = 0):
    """Read the city's most recent source file with a given header_row and return
    headers + sample values + current alias mapping. Powers the Header Mapper UI.
    """
    city = db.cities.find_one({"slug": slug}, {"_id": 0})
    if not city:
        raise HTTPException(404, "unknown city")

    # Pick the most recently received file for this city
    sf = db.source_files.find_one({"city_id": slug}, sort=[("received_at", -1)])
    if not sf or not sf.get("local_path") or not Path(sf["local_path"]).exists():
        raise HTTPException(404, "no source file on disk for this city; upload one first")

    # Lazy import to keep API startup cheap
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "normalizer"))
    from normalize import preview_headers  # type: ignore

    preview = preview_headers(Path(sf["local_path"]), header_row=header_row)
    aliases = {k.lower(): v for k, v in (city.get("column_aliases") or {}).items()}
    for h in preview["headers"]:
        h["current_alias"] = aliases.get(h["header"].strip().lower())

    return {
        "slug": slug,
        "file": {"name": sf.get("filename"), "received_at": sf.get("received_at")},
        "header_row": preview["header_row"],
        "total_rows": preview["total_rows"],
        "headers": preview["headers"],
        "canonical_fields": CANONICAL_FIELDS,
        "current_header_row": int(city.get("header_row", 0)),
    }


class MappingPayload(BaseModel):
    header_row: int = 0
    column_aliases: dict[str, str]


@app.post("/cities/{slug}/mapping")
def save_city_mapping(slug: str, payload: MappingPayload):
    """Persist the user's mapping back to the YAML file AND the DB, then
    re-queue every source file we have for this city so the dashboard
    refills with corrected data.
    """
    yaml_path = CITIES_DIR / f"{slug}.yaml"
    if not yaml_path.exists():
        raise HTTPException(404, f"no YAML for {slug}")

    with yaml_path.open() as f:
        cfg = yaml.safe_load(f)

    # Drop "ignore" mappings — they're just absent aliases
    cleaned = {k: v for k, v in payload.column_aliases.items() if v and v != "ignore"}
    cfg["column_aliases"] = cleaned
    cfg["header_row"] = payload.header_row

    with yaml_path.open("w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

    db.cities.update_one({"slug": slug}, {"$set": cfg}, upsert=True)

    # Re-queue every source file for this city so the normalizer re-runs
    requeued = 0
    for sf in db.source_files.find({"city_id": slug}):
        db.jobs.insert_one({
            "type": "normalize",
            "status": "queued",
            "city_slug": slug,
            "s3_key": sf.get("s3_key"),
            "local_path": sf.get("local_path"),
            "claim_at": None,
            "created_at": datetime.utcnow(),
        })
        requeued += 1

    return {"saved": True, "requeued_files": requeued, "alias_count": len(cleaned)}


@app.get("/cities/near")
def cities_near(lng: float, lat: float, radius_miles: float = 20.0):
    """List cities whose centroid is within radius of (lng, lat).
    Use case: sales rep clicks a point on the map, sees which cities serve it.
    """
    # 1 degree ~= 69 miles in MN latitudes; we use a 2dsphere on centroid-as-point.
    radius_meters = radius_miles * 1609.34
    pipeline = [
        {"$match": {"centroid": {"$exists": True, "$ne": None}}},
        {"$project": {
            "_id": 0,
            "slug": 1,
            "name": 1,
            "vendor": 1,
            "strategy": 1,
            "centroid": 1,
        }},
    ]
    candidates = list(db.cities.aggregate(pipeline))

    # Compute distance in Python (Mongo $geoNear needs centroid stored as GeoJSON);
    # we kept it as a simple [lng, lat] array, so do this client-side. Cheap at N=180.
    from math import asin, cos, radians, sin, sqrt
    def haversine_mi(lng1, lat1, lng2, lat2):
        R = 3958.8
        dlat = radians(lat2 - lat1)
        dlng = radians(lng2 - lng1)
        a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlng/2)**2
        return 2 * R * asin(sqrt(a))

    out = []
    for c in candidates:
        clng, clat = c["centroid"]
        d = haversine_mi(lng, lat, clng, clat)
        if d <= radius_miles:
            out.append({**c, "distance_miles": round(d, 1)})
    out.sort(key=lambda x: x["distance_miles"])
    return {"cities": out, "radius_miles": radius_miles, "center": [lng, lat]}


@app.get("/pipeline/kanban")
def pipeline_kanban():
    """Compute per-city stage. The dashboard renders this as 5 columns."""
    cities = list(db.cities.find({}, {"_id": 0}))
    out = []
    for c in cities:
        slug = c["slug"]
        permits = db.permits.count_documents({"city_id": slug})
        files = db.source_files.count_documents({"city_id": slug})
        rejects = db.rejected_rows.count_documents({"city_id": slug})
        last_file = db.source_files.find_one({"city_id": slug}, sort=[("received_at", -1)]) or {}
        last_outreach = db.outreach_requests.find_one({"city_slug": slug}, sort=[("sent_at", -1)]) or {}

        # Stage logic — computed, not stored
        if permits > 0 and rejects == 0:
            stage = "live"
        elif permits > 0 and rejects > 0:
            stage = "needs_review"
        elif files > 0 and permits == 0:
            stage = "data_received"  # uploaded but normalizer hasn't finished or rejected all rows
        elif last_outreach.get("status") in ("sent", "awaiting"):
            stage = "awaiting_data"
        elif c.get("strategy") == "portal_scrape":
            stage = "awaiting_data"  # portal cities skip outreach
        else:
            stage = "not_contacted"

        out.append({
            "slug": slug,
            "name": c["name"],
            "strategy": c.get("strategy", "manual_upload"),
            "stage": stage,
            "permits": permits,
            "files": files,
            "rejects": rejects,
            "last_file_at": last_file.get("received_at"),
            "last_outreach_at": last_outreach.get("sent_at"),
            "last_outreach_status": last_outreach.get("status"),
            "contact_email": c.get("contact_email"),
            "auto_send": c.get("auto_send", False),
        })
    return {"cities": out}


@app.get("/pipeline/rejects")
def list_rejects(city: Optional[str] = None, limit: int = 100):
    """Rejected rows for the review queue. Each carries the raw row + reasons."""
    q: dict = {}
    if city:
        q["city_id"] = city

    by_reason = list(db.rejected_rows.aggregate([
        {"$match": q},
        {"$unwind": "$reasons"},
        {"$group": {"_id": "$reasons", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    by_city = list(db.rejected_rows.aggregate([
        {"$match": q},
        {"$group": {"_id": "$city_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    samples = list(db.rejected_rows.find(q, {"_id": 0}).limit(limit))
    total = db.rejected_rows.count_documents(q)
    return {"total": total, "by_reason": by_reason, "by_city": by_city, "samples": samples}


@app.get("/pipeline/summaries")
def list_summaries(limit: int = 50):
    """Per-file diagnostics from the normalizer (accepted/rejected counts, unmapped headers)."""
    rows = list(db.normalize_summaries.find({}, {"_id": 0}).limit(limit))
    return {"summaries": rows}


@app.get("/pipeline/city_status")
def city_status():
    """Per-city pipeline state: last file received, last permit ingested, counts."""
    cities = list(db.cities.find({}, {"_id": 0, "slug": 1, "name": 1, "strategy": 1, "status": 1}))
    rows = []
    for c in cities:
        slug = c["slug"]
        last_file = db.source_files.find_one(
            {"city_id": slug}, sort=[("received_at", -1)]
        ) or {}
        last_outreach = db.outreach_requests.find_one(
            {"city_slug": slug}, sort=[("sent_at", -1)]
        ) or {}
        rows.append({
            **c,
            "permits": db.permits.count_documents({"city_id": slug}),
            "files_received": db.source_files.count_documents({"city_id": slug}),
            "last_file_at": last_file.get("received_at"),
            "last_outreach_at": last_outreach.get("sent_at"),
            "last_outreach_status": last_outreach.get("status"),
        })
    return {"cities": rows}
