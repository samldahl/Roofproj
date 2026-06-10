import { useEffect, useMemo, useState } from "react";
import {
  fetchCities, fetchKanban, queueOutreach, uploadFile,
  type KanbanCity, type Stage,
} from "../api";
import type { City } from "../types";
import { HeaderMapper } from "./HeaderMapper";

const STAGES: { id: Stage; label: string; hint: string; accent: string }[] = [
  { id: "not_contacted", label: "Not contacted", hint: "Send DPA or wire portal", accent: "#9ca3af" },
  { id: "awaiting_data", label: "Awaiting data", hint: "Outreach sent / scrape pending", accent: "#3b82f6" },
  { id: "data_received", label: "Data received", hint: "File in, not normalized yet", accent: "#8b5cf6" },
  { id: "needs_review", label: "Needs review", hint: "Rejected rows — tune YAML", accent: "#f59e0b" },
  { id: "live", label: "Live", hint: "Permits in DB, no rejects", accent: "#16a34a" },
];

export function Kanban() {
  const [cards, setCards] = useState<KanbanCity[]>([]);
  const [cities, setCities] = useState<City[]>([]);
  const [selected, setSelected] = useState<KanbanCity | null>(null);

  const refresh = () => {
    fetchKanban().then(setCards).catch(() => {});
    fetchCities().then(setCities).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, []);

  const byStage = useMemo(() => {
    const m: Record<Stage, KanbanCity[]> = {
      not_contacted: [], awaiting_data: [], data_received: [], needs_review: [], live: [],
    };
    cards.forEach((c) => m[c.stage].push(c));
    return m;
  }, [cards]);

  return (
    <div className="kanban">
      <div className="kanban-board">
        {STAGES.map((s) => (
          <div key={s.id} className="kanban-col">
            <div className="kanban-col-head" style={{ borderTop: `3px solid ${s.accent}` }}>
              <div className="kanban-col-title">
                {s.label} <span className="kanban-col-count">{byStage[s.id].length}</span>
              </div>
              <div className="kanban-col-hint">{s.hint}</div>
            </div>
            <div className="kanban-col-body">
              {byStage[s.id].length === 0 && <div className="muted small">—</div>}
              {byStage[s.id].map((c) => (
                <CityCard key={c.slug} c={c} onClick={() => setSelected(c)} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <CityDrawer
          card={selected}
          cities={cities}
          onClose={() => setSelected(null)}
          onAction={() => { refresh(); }}
        />
      )}
    </div>
  );
}

function CityCard({ c, onClick }: { c: KanbanCity; onClick: () => void }) {
  const fmt = (d: string | null) => (d ? new Date(d).toLocaleDateString() : null);
  return (
    <div className="kcard" onClick={onClick}>
      <div className="kcard-top">
        <strong>{c.name}</strong>
        <span className={`pill pill-${c.strategy}`}>{c.strategy}</span>
      </div>
      <div className="kcard-stats">
        <span title="permits">📍 {c.permits}</span>
        <span title="files">📄 {c.files}</span>
        {c.rejects > 0 && <span className="warn-chip" title="rejected rows">⚠ {c.rejects}</span>}
      </div>
      <div className="kcard-meta">
        {c.last_file_at && <span>file {fmt(c.last_file_at)}</span>}
        {c.last_outreach_at && <span>outreach {fmt(c.last_outreach_at)}</span>}
      </div>
    </div>
  );
}

function CityDrawer({ card, cities, onClose, onAction }: {
  card: KanbanCity; cities: City[]; onClose: () => void; onAction: () => void;
}) {
  const cityCfg = cities.find((c) => c.slug === card.slug);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [showMapper, setShowMapper] = useState(false);

  const handleUpload = async (f: File | null) => {
    if (!f) return;
    setBusy(true); setStatus(null);
    try {
      const r = await uploadFile(card.slug, f);
      setStatus(`Queued ${f.name}`);
      onAction();
    } catch (e: any) { setStatus(`Failed: ${e.message ?? e}`); }
    finally { setBusy(false); }
  };

  const handleOutreach = async () => {
    setBusy(true);
    try { await queueOutreach(card.slug); setStatus("Outreach queued"); onAction(); }
    finally { setBusy(false); }
  };

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <h3>{card.name}</h3>
          <button onClick={onClose} className="close">×</button>
        </div>
        <div className="drawer-body">
          <div className="kv"><span>Strategy</span><span>{card.strategy}</span></div>
          <div className="kv"><span>Stage</span><span>{card.stage}</span></div>
          <div className="kv"><span>Contact</span><span>{card.contact_email ?? "—"}</span></div>
          <div className="kv"><span>Permits</span><span>{card.permits}</span></div>
          <div className="kv"><span>Files</span><span>{card.files}</span></div>
          <div className="kv"><span>Rejects</span><span>{card.rejects}</span></div>

          <h4>Actions</h4>
          {(card.strategy === "email_reply" || card.strategy === "manual_upload") && (
            <div className="action">
              <button onClick={handleOutreach} disabled={busy || !card.contact_email}>
                Send DPA request
              </button>
            </div>
          )}
          <div className="action">
            <label>Upload XLSX/CSV</label>
            <input
              type="file"
              accept=".xls,.xlsx,.csv"
              disabled={busy}
              onChange={(e) => handleUpload(e.target.files?.[0] ?? null)}
            />
          </div>
          {card.strategy === "portal_scrape" && (
            <div className="muted small">
              Portal scrape: run <code>services/scrapers/run_scrape.py {card.slug}</code>
            </div>
          )}

          {card.files > 0 && (
            <div className="action">
              <button onClick={() => setShowMapper(true)} className="btn-primary">
                🗺  Map headers → canonical fields
              </button>
              <div className="muted small">
                Use this when rows are being rejected or columns aren't recognized.
              </div>
            </div>
          )}

          {status && <div className="upload-status">{status}</div>}
        </div>
      </div>

      {showMapper && (
        <HeaderMapper
          citySlug={card.slug}
          cityName={card.name}
          onClose={() => setShowMapper(false)}
          onSaved={onAction}
        />
      )}
    </div>
  );
}
