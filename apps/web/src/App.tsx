import { useEffect, useState } from "react";
import { PermitMap } from "./components/PermitMap";
import { Sidebar } from "./components/Sidebar";
import { Dashboard } from "./components/Dashboard";
import { Kanban } from "./components/Kanban";
import { fetchCities, fetchPermits } from "./api";
import type { City, Filters, Permit } from "./types";

const EMPTY: Filters = { city: "", yearMin: "", yearMax: "", contractor: "" };
type View = "kanban" | "stats" | "map";

export default function App() {
  const [view, setView] = useState<View>("kanban");
  const [cities, setCities] = useState<City[]>([]);
  const [permits, setPermits] = useState<Permit[]>([]);
  const [filters, setFilters] = useState<Filters>(EMPTY);

  useEffect(() => { fetchCities().then(setCities).catch(() => {}); }, []);
  useEffect(() => {
    if (view !== "map") return;
    const t = setTimeout(() => { fetchPermits(filters).then(setPermits).catch(() => {}); }, 250);
    return () => clearTimeout(t);
  }, [filters, view]);

  return (
    <div className="app">
      <header className="topbar">
        <h1>Roofproj</h1>
        <nav className="nav">
          <button
            className={view === "kanban" ? "active" : ""}
            onClick={() => setView("kanban")}
          >Pipeline</button>
          <button
            className={view === "stats" ? "active" : ""}
            onClick={() => setView("stats")}
          >Stats</button>
          <button
            className={view === "map" ? "active" : ""}
            onClick={() => setView("map")}
          >Map</button>
        </nav>
      </header>
      {view === "kanban" ? (
        <Kanban />
      ) : view === "stats" ? (
        <Dashboard />
      ) : (
        <div className="layout">
          <Sidebar
            cities={cities}
            filters={filters}
            setFilters={setFilters}
            permitCount={permits.length}
          />
          <div className="map-wrap">
            <PermitMap permits={permits} />
          </div>
        </div>
      )}
    </div>
  );
}
