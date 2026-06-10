"""Core normalize: XLSX/CSV -> canonical Permit dicts."""
from __future__ import annotations

import hashlib
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml


def load_city_config(slug: str, cities_dir: Path) -> dict[str, Any]:
    path = cities_dir / f"{slug}.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def _coerce_date(v: Any) -> date | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


def _coerce_number(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, str):
            v = v.replace("$", "").replace(",", "").strip()
        f = float(v)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _str_or_none(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def read_table(path: Path, header_row: int = 0) -> pd.DataFrame:
    """Read XLS, XLSX, or CSV into a DataFrame.
    header_row: 0-indexed row that contains the column headers. Some city files have a
    title row at the top — set header_row=1 to skip it.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, header=header_row)
    if suffix == ".xls":
        return pd.read_excel(path, engine="xlrd", header=header_row)
    return pd.read_excel(path, engine="openpyxl", header=header_row)


def preview_headers(path: Path, header_row: int = 0, sample_rows: int = 5) -> dict:
    """For the mapper UI: read the file with a candidate header_row and return
    detected headers, sample values, and inferred type hints.
    """
    df = read_table(path, header_row=header_row)
    headers = []
    for col in df.columns:
        series = df[col].dropna().head(sample_rows)
        samples = []
        for v in series:
            if isinstance(v, (date, datetime)):
                samples.append(v.isoformat())
            else:
                s = str(v)
                samples.append(s[:60])
        headers.append({
            "header": str(col),
            "samples": samples,
            "non_null_count": int(df[col].notna().sum()),
        })
    return {
        "header_row": header_row,
        "total_rows": int(len(df)),
        "headers": headers,
    }


def normalize_rows(
    df: pd.DataFrame,
    city: dict[str, Any],
    source_file_s3: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Returns (accepted, rejected, summary).

    - accepted: list of canonical permit docs ready for upsert.
    - rejected: list of {row_index, raw_row, reasons[]} for the review queue.
    - summary: per-file diagnostics (unmapped headers, counts).
    """
    aliases = {k.strip().lower(): v for k, v in city.get("column_aliases", {}).items()}
    canonical_cols: dict[str, str] = {}
    unmapped_headers: list[str] = []
    for col in df.columns:
        canonical = aliases.get(str(col).strip().lower())
        if canonical:
            canonical_cols[col] = canonical
        else:
            unmapped_headers.append(str(col))

    mapped_canonical = set(canonical_cols.values())
    required = {"permit_number", "address_raw", "issue_date"}
    missing_required = sorted(required - mapped_canonical)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        raw_row = {k: (v.isoformat() if isinstance(v, (date, datetime)) else v)
                   for k, v in row.dropna().to_dict().items()}
        mapped: dict[str, Any] = {}
        for src, canon in canonical_cols.items():
            mapped[canon] = row[src]

        permit_number = _str_or_none(mapped.get("permit_number"))
        address_raw = _str_or_none(mapped.get("address_raw"))
        issue_date = _coerce_date(mapped.get("issue_date"))

        reasons: list[str] = []
        if not permit_number:
            reasons.append("missing_permit_number" if "permit_number" in mapped_canonical
                           else "no_alias_for_permit_number")
        if not address_raw:
            reasons.append("missing_address" if "address_raw" in mapped_canonical
                           else "no_alias_for_address")
        if not issue_date:
            reasons.append("missing_or_unparseable_issue_date" if "issue_date" in mapped_canonical
                           else "no_alias_for_issue_date")

        if reasons:
            rejected.append({
                "city_id": city["slug"],
                "source_file_s3": source_file_s3,
                "row_index": int(idx),
                "raw_row": raw_row,
                "reasons": reasons,
                "unmapped_headers": unmapped_headers,
                "ingested_at": datetime.utcnow().isoformat() + "Z",
            })
            continue

        accepted.append({
            "city_id": city["slug"],
            "permit_number": permit_number,
            "address_raw": address_raw,
            "address": address_raw,
            "issue_date": issue_date.isoformat(),
            "completion_date": (
                d.isoformat() if (d := _coerce_date(mapped.get("completion_date"))) else None
            ),
            "contractor_name": _str_or_none(mapped.get("contractor_name")),
            "contractor_license": _str_or_none(mapped.get("contractor_license")),
            "valuation": _coerce_number(mapped.get("valuation")),
            "status": _str_or_none(mapped.get("status")),
            "work_type": _str_or_none(mapped.get("work_type")),
            "parcel_id": _str_or_none(mapped.get("parcel_id")),
            "location": None,
            "source_file_s3": source_file_s3,
            "raw_row_json": raw_row,
            "ingested_at": datetime.utcnow().isoformat() + "Z",
        })

    summary = {
        "city_id": city["slug"],
        "source_file_s3": source_file_s3,
        "total_rows": int(len(df)),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "mapped_columns": canonical_cols,
        "unmapped_headers": unmapped_headers,
        "missing_required_aliases": missing_required,
    }
    return accepted, rejected, summary


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
