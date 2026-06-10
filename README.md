# Roofproj

A pipeline that turns scattered city permit records into one searchable, mappable
dataset of single-family reroof permits.

---

## Problem

Roofs in Minnesota last ~20 years. A permit issued in 2005 is a sales lead in 2025.
But that data lives in 180+ different city offices, in 180+ different formats:

- Some cities email an XLSX in reply to a Data Practices Act request.
- Some have a web portal where staff click through filters and export to Excel.
- Some only kept records since 2012 and charge by the hour for older data.
- Every spreadsheet has different column names, date formats, and quirks.

Today, our client (Proficient Construction) does this entirely by hand:
write the request, wait, parse the reply, copy rows into a spreadsheet.
It doesn't scale past a few cities, and nothing connects to a map.

## Goal

A single dashboard that shows:

1. **INTAKE** — what files we've received, from which cities, by which method.
2. **NORMALIZE** — what's processing, what failed, why.
3. **OUTPUT** — total permits, by city, by year, plotted on a map.

Cheap to add a new city (just a YAML file). Portable to other states later.
Auditable — every permit links back to the original source file.

## How it works

```
  XLSX/CSV file                MongoDB                Dashboard
  ─────────────                ────────               ──────────
   Manual upload   ─►    db.jobs (queued)
   Email reply      \         │
   Portal scrape     ─►       ▼
                          normalizer worker
                          (parse rows, geocode addresses)
                              │
                              ▼
                          db.permits  ───────► map + filters + stats
```

Three intake channels, one normalizer, one DB, one UI. Add a city = add a
[YAML file](cities/minnetonka.yaml) with its contact and column mapping.

---

## Quickstart (local, 10 minutes)

### Prereqs

- Python 3.11+
- Node 20+
- A free MongoDB Atlas cluster (cloud.mongodb.com → free M0 tier)

### 1. Configure

Create `.env` in the project root:

```
MONGO_URI=mongodb+srv://USER:PASS@cluster.mongodb.net/?appName=RoofData
MONGO_DB=roofproj
UPLOAD_DIR=/tmp/roofproj_uploads
```

### 2. Install

```fish
# API
cd services/api && pip install -r requirements.txt && cd ../..

# Normalizer worker
cd services/normalizer && pip install -r requirements.txt && cd ../..

# Web app
cd apps/web && npm install && cd ../..
```

### 3. One-time DB setup

```fish
# Replace with your URI
mongosh '<YOUR_MONGO_URI>' infra/mongo_indexes.js
```

### 4. Run — three terminals

**Terminal 1 — API** (port 8001):
```fish
cd services/api
uvicorn main:app --reload --port 8001
```

**Terminal 2 — Normalizer worker**:
```fish
cd services/normalizer
python worker.py
```

**Terminal 3 — Web dashboard** (port 5174):
```fish
cd apps/web
npm run dev
```

### 5. Load city configs (one-time, fourth terminal)

```fish
curl -X POST http://localhost:8001/cities/sync
```

Returns `{"synced": 2}`. The Eden Prairie and Minnetonka cities are now in Mongo.

### 6. Use it

1. Open <http://localhost:5174>
2. **Pipeline view** is the default — three columns: INTAKE / NORMALIZE / OUTPUT
3. In the **INTAKE → Drop a file** widget:
   - Pick a city
   - Upload one of the files from [raw_samples/](raw_samples/)
4. Watch:
   - NORMALIZE column: Queued → Running → Done
   - OUTPUT column: total permits ticks up
   - City status table at the bottom updates
5. Switch to **Map view** → see pins (if addresses geocoded successfully)

---

## What's where

| Path | What |
|---|---|
| [apps/web/](apps/web/) | React + Vite + MapLibre dashboard |
| [services/api/](services/api/) | FastAPI: stats, uploads, outreach actions |
| [services/normalizer/](services/normalizer/) | XLSX/CSV → canonical schema → Mongo |
| [services/scrapers/](services/scrapers/) | Playwright adapters (one per portal vendor) |
| [services/email_intake/](services/email_intake/) | Gmail poller → S3 → enqueue normalize |
| [services/outreach/](services/outreach/) | DPA request sender (manual + auto modes) |
| [packages/schema/](packages/schema/) | Canonical schema (JSON Schema + Pydantic + TS) |
| [cities/](cities/) | Per-city YAML: contact, strategy, column aliases |
| [infra/](infra/) | Mongo indexes, env template |
| [raw_samples/](raw_samples/) | Real XLSX samples from Eden Prairie + Minnetonka |
| [notes2.md](notes2.md) | Full architecture rationale and roadmap |

---

## MVP build order

1. **Week 1 (now)** — manual upload + normalizer + dashboard + map.
   Demo to Tony with the two existing XLSX files.
2. **Week 2** — first portal scraper (Tyler/Minnetonka). Unlocks N cities at once.
3. **Week 3** — Gmail intake: auto-ingest replies to DPA requests.
4. **Week 4** — outreach bot with throttle + kill switch + human-in-loop dashboard.

Manual upload works on day 1 — you can hire a VA to forward city replies into
the dashboard while we build the automated intake channels in parallel.

## What's hard

In rough order of difficulty:

1. **Normalization across 180+ XLSX dialects.** Column names, units, date formats,
   semantic mismatches ("valuation" sometimes includes labor). The moat.
2. **Portal scraper reliability.** Selectors break. Build health monitoring from day 1.
3. **Address geocoding + dedup.** "123 Main St" vs "123 MAIN STREET APT 2".
4. **Hybrid outreach UX.** Auto-send some cities, manual for others, follow-ups, bounces.
5. **Legal/political risk at scale.** Automated DPA requests can attract pushback.

See [notes2.md](notes2.md) for the full discussion.
