import { useEffect, useState } from "react";
import {
  fetchCities, fetchCityStatus, fetchCoverage, fetchPipelineStats, fetchRejects,
  fetchVendors, uploadFile,
  type CityStatusRow, type CoverageStats, type PipelineStats, type RejectsResponse,
  type VendorRow,
} from "../api";
import type { City } from "../types";

const SOURCE_LABELS: Record<string, string> = {
  manual_upload: "Manual upload",
  email_reply: "Email reply",
  portal_scrape: "Portal scrape",
};

export function Dashboard() {
  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [rows, setRows] = useState<CityStatusRow[]>([]);
  const [cities, setCities] = useState<City[]>([]);
  const [rejects, setRejects] = useState<RejectsResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageStats | null>(null);
  const [vendors, setVendors] = useState<VendorRow[]>([]);

  const refresh = () => {
    fetchPipelineStats().then(setStats).catch(() => {});
    fetchCityStatus().then(setRows).catch(() => {});
    fetchCities().then(setCities).catch(() => {});
    fetchRejects().then(setRejects).catch(() => {});
    fetchCoverage().then(setCoverage).catch(() => {});
    fetchVendors().then(setVendors).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="dash">
      <CoverageHeader coverage={coverage} />
      <VendorPanel vendors={vendors} />

      <div className="funnel">
        <IntakeStage stats={stats} cities={cities} onUpload={refresh} />
        <Arrow />
        <ProcessingStage stats={stats} />
        <Arrow />
        <OutputStage stats={stats} />
      </div>

      <h2 className="section-h">Per-city pipeline status</h2>
      <CityTable rows={rows} />

      <h2 className="section-h">Review queue — rejected rows ({rejects?.total ?? 0})</h2>
      <RejectsPanel rejects={rejects} />
    </div>
  );
}

function CoverageHeader({ coverage }: { coverage: CoverageStats | null }) {
  if (!coverage) return null;
  return (
    <div className="coverage-banner">
      <Metric label="Cities targeted" value={coverage.total_cities} big />
      <Metric label="Cities with data" value={`${coverage.cities_with_data} / ${coverage.total_cities}`} />
      <Metric label="Coverage" value={`${coverage.coverage_pct}%`} big />
      <Metric label="Total permits" value={coverage.total_permits.toLocaleString()} />
      <Metric label="Map accuracy (geocoded)" value={`${coverage.map_accuracy_pct}%`}
              warn={coverage.total_permits > 0 && coverage.map_accuracy_pct < 80} />
    </div>
  );
}

function VendorPanel({ vendors }: { vendors: VendorRow[] }) {
  if (vendors.length === 0) return null;
  return (
    <div className="vendor-panel">
      <h3>Platform / vendor concentration</h3>
      <p className="muted small">
        Where to invest scraper effort. One adapter per vendor unlocks every city on that platform.
      </p>
      <table className="vendor-table">
        <thead>
          <tr><th>Vendor</th><th>Cities</th><th>Strategies</th><th>Slugs</th></tr>
        </thead>
        <tbody>
          {vendors.map((v) => (
            <tr key={v.vendor}>
              <td><strong>{v.vendor}</strong></td>
              <td>{v.total}</td>
              <td>
                {Object.entries(v.by_strategy).map(([s, n]) => (
                  <span key={s} className={`pill pill-${s}`}>{s}: {n}</span>
                ))}
              </td>
              <td className="muted small">{v.cities.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Arrow() {
  return <div className="arrow">→</div>;
}

function StageCard({ title, accent, children }: { title: string; accent: string; children: React.ReactNode }) {
  return (
    <div className="stage" style={{ borderTop: `4px solid ${accent}` }}>
      <h3>{title}</h3>
      {children}
    </div>
  );
}

function IntakeStage({ stats, cities, onUpload }: {
  stats: PipelineStats | null;
  cities: City[];
  onUpload: () => void;
}) {
  const [selectedCity, setSelectedCity] = useState("");
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const handleFile = async (f: File | null) => {
    if (!f || !selectedCity) return;
    setUploading(true);
    setStatus(null);
    try {
      const r = await uploadFile(selectedCity, f);
      setStatus(`Queued ${f.name} (sha=${r.sha256.slice(0, 8)})`);
      onUpload();
    } catch (e: any) {
      setStatus(`Failed: ${e.message ?? e}`);
    } finally {
      setUploading(false);
    }
  };

  const bySource = stats?.intake.by_source ?? [];
  const outreach = stats?.intake.outreach_by_status ?? [];

  return (
    <StageCard title="INTAKE" accent="#2563eb">
      <div className="metric-row">
        <Metric label="Files (7d)" value={stats?.intake.files_last_7d ?? "—"} />
        <Metric label="Overdue follow-ups" value={stats?.intake.overdue_followups ?? "—"} warn={(stats?.intake.overdue_followups ?? 0) > 0} />
      </div>

      <h4>Files by source</h4>
      <BarList items={bySource.map((s) => ({
        label: SOURCE_LABELS[s._id] ?? s._id, value: s.count,
      }))} />

      <h4>Outreach by status</h4>
      <BarList items={outreach.map((s) => ({ label: s._id ?? "unknown", value: s.count }))} />

      <h4>Drop a file</h4>
      <div className="upload-box">
        <select value={selectedCity} onChange={(e) => setSelectedCity(e.target.value)}>
          <option value="">— pick city —</option>
          {cities.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
        </select>
        <input
          type="file"
          accept=".xls,.xlsx,.csv"
          disabled={!selectedCity || uploading}
          onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
        />
        {status && <div className="upload-status">{status}</div>}
      </div>
    </StageCard>
  );
}

function ProcessingStage({ stats }: { stats: PipelineStats | null }) {
  const jobs = stats?.processing.jobs_by_status ?? [];
  const queued = jobs.filter((j) => j._id.status === "queued").reduce((s, j) => s + j.count, 0);
  const running = jobs.filter((j) => j._id.status === "running").reduce((s, j) => s + j.count, 0);
  const failed = jobs.filter((j) => j._id.status === "failed").reduce((s, j) => s + j.count, 0);
  const done = jobs.filter((j) => j._id.status === "done").reduce((s, j) => s + j.count, 0);

  return (
    <StageCard title="NORMALIZE" accent="#f59e0b">
      <div className="metric-row">
        <Metric label="Queued" value={queued} />
        <Metric label="Running" value={running} />
        <Metric label="Done" value={done} />
        <Metric label="Failed" value={failed} warn={failed > 0} />
      </div>

      <h4>Recent failures</h4>
      {stats?.processing.recent_failures.length ? (
        <ul className="failures">
          {stats.processing.recent_failures.map((f, i) => (
            <li key={i}>
              <strong>{f.type}</strong> / {f.city_slug}
              <pre>{(f.error ?? "").split("\n").slice(-3).join("\n")}</pre>
            </li>
          ))}
        </ul>
      ) : <div className="muted">none</div>}
    </StageCard>
  );
}

function OutputStage({ stats }: { stats: PipelineStats | null }) {
  const o = stats?.output;
  return (
    <StageCard title="OUTPUT" accent="#16a34a">
      <div className="metric-row">
        <Metric label="Total permits" value={o?.total_permits ?? "—"} big />
        <Metric label="Geocoded" value={o ? `${o.geocoded_pct}%` : "—"} />
      </div>

      <h4>By city</h4>
      <BarList items={(o?.by_city ?? []).map((c) => ({ label: c._id, value: c.count }))} />

      <h4>By issue year</h4>
      <BarList items={(o?.by_year ?? []).map((y) => ({ label: y._id, value: y.count }))} />
    </StageCard>
  );
}

function Metric({ label, value, big, warn }: { label: string; value: any; big?: boolean; warn?: boolean }) {
  return (
    <div className="metric">
      <div className={`metric-v ${big ? "big" : ""} ${warn ? "warn" : ""}`}>{value}</div>
      <div className="metric-l">{label}</div>
    </div>
  );
}

function BarList({ items }: { items: { label: string; value: number }[] }) {
  if (!items.length) return <div className="muted">no data</div>;
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className="bars">
      {items.map((i, idx) => (
        <li key={idx}>
          <span className="bars-label">{i.label}</span>
          <span className="bars-bar" style={{ width: `${(i.value / max) * 100}%` }} />
          <span className="bars-v">{i.value}</span>
        </li>
      ))}
    </ul>
  );
}

const REASON_LABELS: Record<string, string> = {
  no_alias_for_permit_number: "No alias mapped → permit_number (add to city YAML)",
  no_alias_for_address: "No alias mapped → address (add to city YAML)",
  no_alias_for_issue_date: "No alias mapped → issue_date (add to city YAML)",
  missing_permit_number: "Column mapped but row had blank permit_number",
  missing_address: "Column mapped but row had blank address",
  missing_or_unparseable_issue_date: "Date couldn't be parsed",
};

function RejectsPanel({ rejects }: { rejects: RejectsResponse | null }) {
  if (!rejects || rejects.total === 0) {
    return <div className="muted">No rejected rows. (Or no files processed yet.)</div>;
  }
  return (
    <div className="rejects">
      <div className="rejects-summary">
        <div>
          <h4>By reason</h4>
          <BarList items={rejects.by_reason.map((r) => ({
            label: REASON_LABELS[r._id] ?? r._id, value: r.count,
          }))} />
        </div>
        <div>
          <h4>By city</h4>
          <BarList items={rejects.by_city.map((c) => ({ label: c._id, value: c.count }))} />
        </div>
      </div>

      <h4>Sample rejected rows</h4>
      <table className="rejects-table">
        <thead>
          <tr>
            <th>City</th><th>Row #</th><th>Reasons</th><th>Raw row (first cells)</th>
          </tr>
        </thead>
        <tbody>
          {rejects.samples.slice(0, 25).map((r, i) => (
            <tr key={i}>
              <td>{r.city_id}</td>
              <td>{r.row_index}</td>
              <td>{r.reasons.join(", ")}</td>
              <td>
                <code className="raw-row">
                  {Object.entries(r.raw_row).slice(0, 4).map(([k, v]) =>
                    `${k}=${String(v).slice(0, 40)}`).join("  |  ")}
                </code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {rejects.samples[0]?.unmapped_headers?.length ? (
        <div className="unmapped-hint">
          <strong>Headers in the file we didn't recognize:</strong>{" "}
          <code>{rejects.samples[0].unmapped_headers.join(", ")}</code>
          <div className="muted">
            Add the relevant ones to <code>cities/{rejects.samples[0].city_id}.yaml</code> under{" "}
            <code>column_aliases</code>, then re-upload.
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CityTable({ rows }: { rows: CityStatusRow[] }) {
  const fmt = (d: string | null) => (d ? new Date(d).toLocaleDateString() : "—");
  return (
    <table className="city-table">
      <thead>
        <tr>
          <th>City</th><th>Strategy</th><th>Permits</th><th>Files</th>
          <th>Last file</th><th>Last outreach</th><th>Outreach status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.slug}>
            <td>{r.name}</td>
            <td><span className={`pill pill-${r.strategy}`}>{r.strategy}</span></td>
            <td>{r.permits}</td>
            <td>{r.files_received}</td>
            <td>{fmt(r.last_file_at)}</td>
            <td>{fmt(r.last_outreach_at)}</td>
            <td>{r.last_outreach_status ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
