import type { City, Filters, Permit } from "./types";

const base = "/api";

export async function fetchPermits(f: Filters): Promise<Permit[]> {
  const params = new URLSearchParams();
  if (f.city) params.set("city", f.city);
  if (f.yearMin) params.set("year_min", f.yearMin);
  if (f.yearMax) params.set("year_max", f.yearMax);
  if (f.contractor) params.set("contractor", f.contractor);
  const res = await fetch(`${base}/permits?${params}`);
  return (await res.json()).permits as Permit[];
}

export async function fetchCities(): Promise<City[]> {
  return (await (await fetch(`${base}/cities`)).json()).cities;
}

export async function queueOutreach(slug: string) {
  await fetch(`${base}/outreach/send/${slug}`, { method: "POST" });
}

export async function fetchPipelineStats(): Promise<PipelineStats> {
  return await (await fetch(`${base}/pipeline/stats`)).json();
}

export async function fetchCityStatus(): Promise<CityStatusRow[]> {
  return (await (await fetch(`${base}/pipeline/city_status`)).json()).cities;
}

export async function fetchRejects(): Promise<RejectsResponse> {
  return await (await fetch(`${base}/pipeline/rejects`)).json();
}

export async function fetchKanban(): Promise<KanbanCity[]> {
  return (await (await fetch(`${base}/pipeline/kanban`)).json()).cities;
}

export async function fetchCoverage(): Promise<CoverageStats> {
  return await (await fetch(`${base}/stats/coverage`)).json();
}

export async function fetchVendors(): Promise<VendorRow[]> {
  return (await (await fetch(`${base}/stats/vendors`)).json()).vendors;
}

export async function inspectCity(slug: string, headerRow: number): Promise<InspectResponse> {
  const r = await fetch(`${base}/cities/${slug}/inspect?header_row=${headerRow}`);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function saveCityMapping(slug: string, headerRow: number, aliases: Record<string, string>) {
  const r = await fetch(`${base}/cities/${slug}/mapping`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ header_row: headerRow, column_aliases: aliases }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export interface InspectResponse {
  slug: string;
  file: { name: string; received_at: string };
  header_row: number;
  current_header_row: number;
  total_rows: number;
  headers: {
    header: string;
    samples: string[];
    non_null_count: number;
    current_alias: string | null;
  }[];
  canonical_fields: string[];
}

export async function fetchCitiesNear(lng: number, lat: number, miles: number) {
  const p = new URLSearchParams({ lng: String(lng), lat: String(lat), radius_miles: String(miles) });
  return await (await fetch(`${base}/cities/near?${p}`)).json();
}

export interface CoverageStats {
  total_cities: number;
  cities_with_files: number;
  cities_with_data: number;
  coverage_pct: number;
  total_permits: number;
  geocoded_permits: number;
  map_accuracy_pct: number;
  per_city: {
    slug: string;
    permits: number;
    geocoded: number;
    geocoded_pct: number;
    rejects: number;
    reject_rate: number;
    data_starts_at: number | null;
  }[];
}

export interface VendorRow {
  vendor: string;
  total: number;
  by_strategy: Record<string, number>;
  cities: string[];
}

export type Stage = "not_contacted" | "awaiting_data" | "data_received" | "needs_review" | "live";

export interface KanbanCity {
  slug: string;
  name: string;
  strategy: string;
  stage: Stage;
  permits: number;
  files: number;
  rejects: number;
  last_file_at: string | null;
  last_outreach_at: string | null;
  last_outreach_status: string | null;
  contact_email: string | null;
  auto_send: boolean;
}

export async function uploadFile(citySlug: string, file: File) {
  const fd = new FormData();
  fd.append("city_slug", citySlug);
  fd.append("file", file);
  const res = await fetch(`${base}/intake/upload`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

export interface PipelineStats {
  intake: {
    by_source: { _id: string; count: number }[];
    files_last_7d: number;
    outreach_by_status: { _id: string; count: number }[];
    overdue_followups: number;
  };
  processing: {
    jobs_by_status: { _id: { type: string; status: string }; count: number }[];
    recent_failures: { type: string; city_slug: string; error: string; finished_at: string }[];
  };
  output: {
    total_permits: number;
    geocoded_permits: number;
    geocoded_pct: number;
    by_city: { _id: string; count: number }[];
    by_year: { _id: string; count: number }[];
  };
}

export interface RejectsResponse {
  total: number;
  by_reason: { _id: string; count: number }[];
  by_city: { _id: string; count: number }[];
  samples: {
    city_id: string;
    source_file_s3: string;
    row_index: number;
    reasons: string[];
    unmapped_headers: string[];
    raw_row: Record<string, unknown>;
  }[];
}

export interface CityStatusRow {
  slug: string;
  name: string;
  strategy: string;
  status: string;
  permits: number;
  files_received: number;
  last_file_at: string | null;
  last_outreach_at: string | null;
  last_outreach_status: string | null;
}
