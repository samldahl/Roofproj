"""CLI: run a scrape for one city, upload to S3, enqueue normalize job.

Usage:
    python run_scrape.py <city_slug>
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import boto3
import yaml
from dotenv import load_dotenv
from pymongo import MongoClient

from adapters import tyler

ADAPTERS = {"tyler": tyler}
CITIES_DIR = Path(__file__).resolve().parents[2] / "cities"


def main(slug: str) -> None:
    load_dotenv()
    with (CITIES_DIR / f"{slug}.yaml").open() as f:
        city = yaml.safe_load(f)
    adapter = ADAPTERS[city["vendor"]]

    with tempfile.TemporaryDirectory() as td:
        out_path = adapter.scrape(city, Path(td))
        bucket = os.environ["S3_BUCKET"]
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        s3_key = f"raw/{slug}/scrape/{ts}_{out_path.name}"

        s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT") or None,
            aws_access_key_id=os.environ["S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["S3_SECRET_KEY"],
            region_name=os.getenv("S3_REGION", "auto"),
        )
        s3.upload_file(str(out_path), bucket, s3_key)

        db = MongoClient(os.environ["MONGO_URI"])[os.getenv("MONGO_DB", "roofproj")]
        db.jobs.insert_one({
            "type": "normalize",
            "status": "queued",
            "city_slug": slug,
            "s3_key": s3_key,
            "claim_at": None,
            "created_at": datetime.utcnow(),
        })
        print(f"uploaded {s3_key} and queued normalize job")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
