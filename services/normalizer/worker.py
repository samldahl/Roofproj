"""Long-running worker: claims jobs from db.jobs, runs normalize.

Job document:
    { _id, type: "normalize", status: "queued"|"running"|"done"|"failed",
      city_slug, s3_key, claim_at, created_at, error? }
"""
from __future__ import annotations

import os
import tempfile
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import boto3
from dotenv import load_dotenv

from db import get_db, save_rejected, save_summary, upsert_permits
from geocode import geocode
from normalize import load_city_config, normalize_rows, read_table

CITIES_DIR = Path(__file__).resolve().parents[2] / "cities"
CLAIM_TTL = timedelta(minutes=10)


def s3_client():
    """Lazy: only built when a job actually needs S3.
    Local-only mode (no S3 env vars) is fully supported for manual uploads.
    """
    if not os.getenv("S3_ACCESS_KEY") or not os.getenv("S3_SECRET_KEY"):
        return None
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT") or None,
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.getenv("S3_REGION", "auto"),
    )


def claim_job(db):
    now = datetime.utcnow()
    return db.jobs.find_one_and_update(
        {
            "type": "normalize",
            "status": {"$in": ["queued", "running"]},
            "$or": [{"claim_at": None}, {"claim_at": {"$lt": now}}],
        },
        {"$set": {"status": "running", "claim_at": now + CLAIM_TTL}},
        sort=[("created_at", 1)],
    )


def run_job(db, s3, job: dict) -> None:
    slug = job["city_slug"]
    s3_key = job["s3_key"]
    city = load_city_config(slug, CITIES_DIR)

    header_row = int(city.get("header_row", 0))
    # Prefer local path (manual upload skips S3 round-trip)
    local_path = job.get("local_path")
    if local_path and Path(local_path).exists():
        df = read_table(Path(local_path), header_row=header_row)
    else:
        if s3 is None:
            raise RuntimeError(
                f"Job {job['_id']} has no local_path and S3 is not configured. "
                "Either configure S3_* env vars or re-upload via the dashboard."
            )
        with tempfile.NamedTemporaryFile(suffix=Path(s3_key).suffix, delete=False) as tmp:
            s3.download_file(os.environ["S3_BUCKET"], s3_key, tmp.name)
            df = read_table(Path(tmp.name), header_row=header_row)

    accepted, rejected, summary = normalize_rows(df, city, source_file_s3=s3_key)
    for p in accepted:
        coords = geocode(p["address_raw"], city=city["name"])
        if coords:
            p["location"] = {"type": "Point", "coordinates": coords}

    upserted, modified = upsert_permits(db, accepted)
    save_rejected(db, rejected)
    save_summary(db, summary)
    db.jobs.update_one(
        {"_id": job["_id"]},
        {"$set": {"status": "done", "finished_at": datetime.utcnow(),
                  "result": {"upserted": upserted, "modified": modified,
                             "accepted": len(accepted), "rejected": len(rejected),
                             "total_rows": summary["total_rows"],
                             "missing_required_aliases": summary["missing_required_aliases"]}}},
    )


def main() -> None:
    load_dotenv()
    db = get_db()
    s3 = s3_client()
    print(f"normalizer worker started (s3 {'enabled' if s3 else 'disabled, local-only'})")
    while True:
        job = claim_job(db)
        if not job:
            time.sleep(5)
            continue
        print(f"claimed job {job['_id']} city={job['city_slug']}")
        try:
            run_job(db, s3, job)
            print(f"done {job['_id']}")
        except Exception:
            db.jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {"status": "failed", "error": traceback.format_exc(),
                          "finished_at": datetime.utcnow()}},
            )
            print(f"failed {job['_id']}")


if __name__ == "__main__":
    main()
