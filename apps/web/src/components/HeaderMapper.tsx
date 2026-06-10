import { useEffect, useState } from "react";
import { inspectCity, saveCityMapping, type InspectResponse } from "../api";

interface Props {
  citySlug: string;
  cityName: string;
  onClose: () => void;
  onSaved: () => void;
}

const REQUIRED = new Set(["permit_number", "address_raw", "issue_date"]);

export function HeaderMapper({ citySlug, cityName, onClose, onSaved }: Props) {
  const [headerRow, setHeaderRow] = useState(0);
  const [data, setData] = useState<InspectResponse | null>(null);
  const [aliases, setAliases] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = async (hr: number) => {
    setErr(null);
    try {
      const r = await inspectCity(citySlug, hr);
      setData(r);
      // Seed aliases with current mapping
      const seed: Record<string, string> = {};
      r.headers.forEach((h) => { seed[h.header] = h.current_alias ?? "ignore"; });
      setAliases(seed);
      setHeaderRow(r.header_row);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    }
  };

  useEffect(() => { load(0); }, [citySlug]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await saveCityMapping(citySlug, headerRow, aliases);
      onSaved();
      onClose();
      alert(`Saved. Re-queued ${result.requeued_files} file(s) for reprocessing.`);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  const mappedCanonical = new Set(Object.values(aliases).filter((v) => v && v !== "ignore"));
  const missingRequired = [...REQUIRED].filter((f) => !mappedCanonical.has(f));

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="mapper" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <h3>Header mapper — {cityName}</h3>
          <button onClick={onClose} className="close">×</button>
        </div>

        {err && <div className="err-banner">{err}</div>}

        {!data ? (
          <div className="mapper-body"><div className="muted">Loading…</div></div>
        ) : (
          <div className="mapper-body">
            <div className="mapper-controls">
              <div>
                <label>Header row (0-indexed)</label>
                <input
                  type="number"
                  min={0}
                  value={headerRow}
                  onChange={(e) => setHeaderRow(parseInt(e.target.value || "0"))}
                />
                <button onClick={() => load(headerRow)} style={{ marginLeft: 8 }}>
                  Reload preview
                </button>
              </div>
              <div className="mapper-meta">
                <div><strong>File:</strong> {data.file.name}</div>
                <div><strong>Rows:</strong> {data.total_rows}</div>
              </div>
            </div>

            <div className="required-status">
              {missingRequired.length === 0 ? (
                <span className="ok">✓ All required fields mapped</span>
              ) : (
                <span className="warn">
                  ⚠ Still need to map: <code>{missingRequired.join(", ")}</code>
                </span>
              )}
            </div>

            <table className="mapper-table">
              <thead>
                <tr>
                  <th style={{ width: "20%" }}>File header</th>
                  <th style={{ width: "25%" }}>Map to canonical field</th>
                  <th style={{ width: "10%" }}>Filled %</th>
                  <th>Sample values</th>
                </tr>
              </thead>
              <tbody>
                {data.headers.map((h) => {
                  const filledPct = data.total_rows
                    ? Math.round((100 * h.non_null_count) / data.total_rows)
                    : 0;
                  const v = aliases[h.header] ?? "ignore";
                  const isMapped = v !== "ignore";
                  return (
                    <tr key={h.header} className={isMapped ? "mapped-row" : ""}>
                      <td className="hdr-cell"><code>{h.header}</code></td>
                      <td>
                        <select
                          value={v}
                          onChange={(e) =>
                            setAliases((a) => ({ ...a, [h.header]: e.target.value }))
                          }
                        >
                          {data.canonical_fields.map((f) => (
                            <option key={f} value={f}>
                              {f === "ignore" ? "— ignore —" : f}
                              {REQUIRED.has(f) ? " *" : ""}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="muted small">{filledPct}%</td>
                      <td className="samples">
                        {h.samples.slice(0, 3).map((s, i) => (
                          <span key={i} className="sample-chip">{s}</span>
                        ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="mapper-foot">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={handleSave} disabled={saving || !data} className="btn-primary">
            {saving ? "Saving…" : "Save & re-normalize"}
          </button>
        </div>
      </div>
    </div>
  );
}
