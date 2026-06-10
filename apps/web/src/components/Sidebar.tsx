import { useState } from "react";
import type { City, Filters } from "../types";
import { fetchCitiesNear, queueOutreach } from "../api";

interface Props {
  cities: City[];
  filters: Filters;
  setFilters: (f: Filters) => void;
  permitCount: number;
}

interface NearbyResult {
  cities: { slug: string; name: string; vendor: string | null; distance_miles: number }[];
  center: [number, number];
  radius_miles: number;
}

export function Sidebar({ cities, filters, setFilters, permitCount }: Props) {
  const [lat, setLat] = useState("44.977");
  const [lng, setLng] = useState("-93.265");
  const [radius, setRadius] = useState("20");
  const [nearby, setNearby] = useState<NearbyResult | null>(null);

  const handleSearch = async () => {
    const res = await fetchCitiesNear(parseFloat(lng), parseFloat(lat), parseFloat(radius));
    setNearby(res);
  };

  return (
    <aside className="sidebar">
      <div>{permitCount} permits</div>

      <h2>Filters</h2>
      <label>
        City
        <select
          value={filters.city}
          onChange={(e) => setFilters({ ...filters, city: e.target.value })}
        >
          <option value="">All</option>
          {cities.map((c) => (
            <option key={c.slug} value={c.slug}>{c.name}</option>
          ))}
        </select>
      </label>
      <label>
        Year min
        <input
          type="number"
          value={filters.yearMin}
          onChange={(e) => setFilters({ ...filters, yearMin: e.target.value })}
        />
      </label>
      <label>
        Year max
        <input
          type="number"
          value={filters.yearMax}
          onChange={(e) => setFilters({ ...filters, yearMax: e.target.value })}
        />
      </label>
      <label>
        Contractor
        <input
          value={filters.contractor}
          onChange={(e) => setFilters({ ...filters, contractor: e.target.value })}
        />
      </label>

      <h2>Cities near a point</h2>
      <label>Lat <input value={lat} onChange={(e) => setLat(e.target.value)} /></label>
      <label>Lng <input value={lng} onChange={(e) => setLng(e.target.value)} /></label>
      <label>Radius (mi) <input value={radius} onChange={(e) => setRadius(e.target.value)} /></label>
      <button onClick={handleSearch} style={{ marginTop: 4, fontSize: 12 }}>Find cities</button>
      {nearby && (
        <ul style={{ listStyle: "none", padding: 0, marginTop: 6, fontSize: 12 }}>
          {nearby.cities.length === 0 && <li className="muted">none within {nearby.radius_miles} mi</li>}
          {nearby.cities.map((c) => (
            <li key={c.slug} style={{ padding: "2px 0" }}>
              {c.name} — <span style={{ color: "#6b7280" }}>{c.distance_miles} mi {c.vendor ?? ""}</span>
            </li>
          ))}
        </ul>
      )}

      <h2>Outreach</h2>
      {cities.map((c) => (
        <div key={c.slug} style={{ display: "flex", justifyContent: "space-between", margin: "4px 0" }}>
          <span style={{ fontSize: 13 }}>{c.name}</span>
          <button onClick={() => queueOutreach(c.slug)} style={{ fontSize: 11 }}>
            Send DPA
          </button>
        </div>
      ))}
    </aside>
  );
}
