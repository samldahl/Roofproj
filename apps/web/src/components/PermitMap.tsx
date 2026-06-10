import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import type { Permit } from "../types";

const MN_CENTER: [number, number] = [-93.265, 44.977];

export function PermitMap({ permits }: { permits: Permit[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    mapRef.current = new maplibregl.Map({
      container: ref.current,
      style: "https://demotiles.maplibre.org/style.json",
      center: MN_CENTER,
      zoom: 9,
    });
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const apply = () => {
      const features = permits
        .filter((p) => p.location)
        .map((p) => ({
          type: "Feature" as const,
          geometry: p.location!,
          properties: {
            permit_number: p.permit_number,
            address: p.address,
            issue_year: Number(p.issue_date.slice(0, 4)),
            contractor: p.contractor_name ?? "",
          },
        }));
      const data = { type: "FeatureCollection" as const, features };

      const src = map.getSource("permits") as maplibregl.GeoJSONSource | undefined;
      if (src) {
        src.setData(data);
      } else {
        map.addSource("permits", { type: "geojson", data, cluster: true, clusterRadius: 40 });
        map.addLayer({
          id: "clusters",
          type: "circle",
          source: "permits",
          filter: ["has", "point_count"],
          paint: {
            "circle-color": "#2563eb",
            "circle-radius": ["step", ["get", "point_count"], 14, 25, 18, 100, 24],
            "circle-opacity": 0.75,
          },
        });
        map.addLayer({
          id: "cluster-count",
          type: "symbol",
          source: "permits",
          filter: ["has", "point_count"],
          layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
          paint: { "text-color": "#fff" },
        });
        map.addLayer({
          id: "unclustered",
          type: "circle",
          source: "permits",
          filter: ["!", ["has", "point_count"]],
          paint: {
            "circle-color": [
              "interpolate", ["linear"], ["get", "issue_year"],
              2005, "#fde68a", 2015, "#f97316", 2025, "#b91c1c",
            ],
            "circle-radius": 6,
            "circle-stroke-color": "#fff",
            "circle-stroke-width": 1,
          },
        });
      }
    };

    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [permits]);

  return <div ref={ref} style={{ width: "100%", height: "100%" }} />;
}
