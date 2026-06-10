"""One-shot CLI: ingest a local XLSX/CSV for a given city.

Usage:
    python ingest_file.py <city_slug> <path_to_file>
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from db import get_db, save_rejected, save_summary, upsert_permits
from geocode import geocode
from normalize import file_sha256, load_city_config, normalize_rows, read_table


def main(slug: str, file_path: str) -> None:
    load_dotenv()
    cities_dir = Path(__file__).resolve().parents[2] / "cities"
    path = Path(file_path)

    city = load_city_config(slug, cities_dir)
    df = read_table(path, header_row=int(city.get("header_row", 0)))
    sha = file_sha256(path)
    s3_key = f"raw/{slug}/local/{sha[:12]}_{path.name}"

    accepted, rejected, summary = normalize_rows(df, city, source_file_s3=s3_key)
    print(f"file={path.name}  total={summary['total_rows']}  "
          f"accepted={summary['accepted']}  rejected={summary['rejected']}")
    if summary["missing_required_aliases"]:
        print(f"  ! missing aliases for: {summary['missing_required_aliases']}")
    if summary["unmapped_headers"]:
        print(f"  ! unmapped headers (consider adding): {summary['unmapped_headers']}")

    for p in accepted:
        coords = geocode(p["address_raw"], city=city["name"])
        if coords:
            p["location"] = {"type": "Point", "coordinates": coords}

    db = get_db()
    upserted, modified = upsert_permits(db, accepted)
    save_rejected(db, rejected)
    save_summary(db, summary)
    print(f"upserted={upserted} modified={modified} rejected_saved={len(rejected)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
