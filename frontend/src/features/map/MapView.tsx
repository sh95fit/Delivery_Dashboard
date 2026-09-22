import { useEffect, useRef, useState } from "react";
import type { ManagerRow } from "@/api/types";
import type { RouteResp } from "@/api/routes";
import { getRoute } from "@/api/routes";

const COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c"];

declare global {
  interface Window { google?: any }
}

export default function MapView({ date, managers, stops }: {
  date: string;
  managers: ManagerRow[];
  stops: { lat: number; lng: number; manager_id: number; label: string }[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const layersRef = useRef<any[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [route, setRoute] = useState<RouteResp | null>(null);

  // 지도 초기화
  useEffect(() => {
    if (!ref.current || mapRef.current || !window.google) return;
    mapRef.current = new window.google.maps.Map(ref.current, {
      center: { lat: 37.5665, lng: 126.978 },
      zoom: 12,
    });
  }, []);

  // 핀 그리기 (매니저 색상)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.google) return;
    layersRef.current.forEach((m) => m.setMap(null));
    layersRef.current = [];

    const bounds = new window.google.maps.LatLngBounds();
    stops.forEach((s) => {
      const color = COLORS[s.manager_id % COLORS.length];
      const marker = new window.google.maps.Marker({
        map,
        position: { lat: s.lat, lng: s.lng },
        title: s.label,
        icon: {
          path: window.google.maps.SymbolPath.CIRCLE,
          scale: 7, fillColor: color, fillOpacity: 1,
          strokeColor: "#fff", strokeWeight: 1,
        },
      });
      const info = new window.google.maps.InfoWindow({ content: s.label });
      marker.addListener("click", () => {
        info.open(map, marker);
        setSelected(s.manager_id);
      });
      layersRef.current.push(marker);
      bounds.extend(marker.getPosition());
    });
    if (stops.length) map.fitBounds(bounds);
  }, [stops]);

  // 매니저 선택 시 폴리라인 로드 (캐시 우선)
  useEffect(() => {
    if (selected == null) return;
    let alive = true;
    getRoute(date, selected).then((r) => alive && setRoute(r)).catch(() => alive && setRoute(null));
    return () => { alive = false; };
  }, [selected, date]);

  // 폴리라인 렌더링
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.google || !route?.polyline) return;
    const decoded = window.google.maps.geometry.encoding.decodePath(route.polyline);
    const line = new window.google.maps.Polyline({
      path: decoded, map,
      strokeColor: "#4363d8", strokeOpacity: 0.85, strokeWeight: 4,
    });
    layersRef.current.push(line);
    return () => { line.setMap(null); };
  }, [route]);

  return (
    <div>
      <div ref={ref} style={{ width: "100%", height: 420, borderRadius: 12, border: "1px solid #e5e7eb" }} />
      <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
        {selected != null && route && route.source !== "unavailable" && (
          <span>
            매니저 {selected} — {(route.distance_m / 1000).toFixed(1)}km · {Math.round(route.duration_s / 60)}분
            {route.source === "cache" && " (캐시)"}
          </span>
        )}
        {selected != null && route?.source === "unavailable" && <span>경로 데이터 없음 — 핀만 표시</span>}
      </div>
    </div>
  );
}
