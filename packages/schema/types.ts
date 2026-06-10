// Canonical types for the React frontend. Mirrors permit.schema.json.

export interface GeoPoint {
  type: "Point";
  coordinates: [number, number]; // [lng, lat]
}

export interface Permit {
  city_id: string;
  permit_number: string;
  address: string;
  address_raw?: string | null;
  parcel_id?: string | null;
  issue_date: string; // ISO date
  completion_date?: string | null;
  contractor_name?: string | null;
  contractor_license?: string | null;
  valuation?: number | null;
  status?: string | null;
  work_type?: string | null;
  location?: GeoPoint | null;
  source_file_s3: string;
  ingested_at: string;
}

export interface City {
  slug: string;
  name: string;
  state: string;
  contact_email?: string | null;
  strategy: "email_reply" | "portal_scrape" | "manual_upload";
  vendor?: string | null;
  auto_send: boolean;
  status: string;
}
