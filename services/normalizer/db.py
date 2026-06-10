"""MongoDB connection + upsert helpers."""
from __future__ import annotations

import os
from typing import Any

from pymongo import MongoClient, UpdateOne


def get_db():
    uri = os.environ["MONGO_URI"]
    name = os.getenv("MONGO_DB", "roofproj")
    return MongoClient(uri)[name]


def upsert_permits(db, permits: list[dict[str, Any]]) -> tuple[int, int]:
    """Returns (upserted, modified)."""
    if not permits:
        return (0, 0)
    ops = [
        UpdateOne(
            {"city_id": p["city_id"], "permit_number": p["permit_number"]},
            {"$set": p},
            upsert=True,
        )
        for p in permits
    ]
    res = db.permits.bulk_write(ops, ordered=False)
    return (res.upserted_count, res.modified_count)


def save_rejected(db, rejected: list[dict[str, Any]]) -> int:
    """Replace any prior rejects for the same source file, then insert fresh."""
    if not rejected:
        return 0
    s3_key = rejected[0]["source_file_s3"]
    db.rejected_rows.delete_many({"source_file_s3": s3_key})
    db.rejected_rows.insert_many(rejected)
    return len(rejected)


def save_summary(db, summary: dict[str, Any]) -> None:
    db.normalize_summaries.update_one(
        {"source_file_s3": summary["source_file_s3"]},
        {"$set": summary},
        upsert=True,
    )
