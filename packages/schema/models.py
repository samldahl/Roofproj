"""Canonical Pydantic models. Mirrors permit.schema.json."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: list[float]  # [lng, lat]


class Permit(BaseModel):
    city_id: str
    permit_number: str
    address: str
    address_raw: Optional[str] = None
    parcel_id: Optional[str] = None
    issue_date: date
    completion_date: Optional[date] = None
    contractor_name: Optional[str] = None
    contractor_license: Optional[str] = None
    valuation: Optional[float] = None
    status: Optional[str] = None
    work_type: Optional[str] = None
    location: Optional[GeoPoint] = None
    source_file_s3: str
    raw_row_json: dict[str, Any] = Field(default_factory=dict)
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


class City(BaseModel):
    slug: str
    name: str
    state: str = "MN"
    contact_email: Optional[str] = None
    strategy: Literal["email_reply", "portal_scrape", "manual_upload"]
    vendor: Optional[str] = None  # tyler_epermits, civicplus, opengov, accela, custom
    portal_config: dict[str, Any] = Field(default_factory=dict)
    portal_steps: list[str] = Field(default_factory=list)  # human-followable instructions
    column_aliases: dict[str, str] = Field(default_factory=dict)
    auto_send: bool = False
    status: str = "pending"
    notes: Optional[str] = None

    # Data horizon / policy (from real city replies)
    data_starts_at: Optional[int] = None  # earliest year their software has
    paid_pre_data_available: bool = False
    paid_records_cost_note: Optional[str] = None

    # Geo (for radius search; can be auto-derived from permits)
    centroid: Optional[list[float]] = None  # [lng, lat]
