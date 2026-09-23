import { useEffect, useMemo, useRef } from "react";
import type { RouteSummary, StopPoint } from "@/api/types";

const DEFAULT_CENTER = { lat: 37.5665, lng: 126.9780 };

declare global {
  interface Window {
    naver?: any;
  }
}

type StopGroup = {
  key: string;
  latitude: number;
  longitude: number;
  managerColor?: string | null;
  items: StopPoint[];
};

function escapeHtml(value: string | null | undefined) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function lineupText(stop: StopPoint) {
  const parts = Object.values(stop.lineups)
    .filter((x) => x.qty > 0)
    .map((x) => `${x.name} ${x.qty}`);
  return parts.join(" / ");
}

function loadNaverMaps(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.naver?.maps) return resolve();

    const existing = document.getElementById("naver-maps-script") as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("NAVER Maps 스크립트 로드 실패")));
      return;
    }

    const keyId = import.meta.env.VITE_NAVER_MAP_KEY_ID;
    if (!keyId) {
      reject(new Error("VITE_NAVER_MAP_KEY_ID가 없습니다"));
      return;
    }

    const script = document.createElement("script");
    script.id = "naver-maps-script";
    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${keyId}`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("NAVER Maps 스크립트 로드 실패"));
    document.head.appendChild(script);
  });
}

function buildPopupHtml(group: StopGroup) {
  const title =
    group.items.length > 1
      ? `동일 위치 배송 ${group.items.length}건`
      : escapeHtml(group.items[0]?.address_name ?? "배송지");

  const itemsHtml = group.items
    .slice()
    .sort((a, b) => {
      const at = a.delivery_time ?? "99:99";
      const bt = b.delivery_time ?? "99:99";
      if (at !== bt) return at.localeCompare(bt);

      const an = a.address_name ?? "";
      const bn = b.address_name ?? "";
      if (an !== bn) return an.localeCompare(bn);

      return (a.detail_address ?? "").localeCompare(b.detail_address ?? "");
    })
    .map((stop, idx) => {
      const name = escapeHtml(stop.address_name?.trim() || `주소ID ${stop.address_id}`);
      const detail = stop.detail_address?.trim() ? escapeHtml(stop.detail_address) : "";
      const manager = escapeHtml(stop.manager_name ?? "미배정");
      const time = escapeHtml(stop.delivery_time ?? "없음");
      const lineup = escapeHtml(lineupText(stop) || "없음");

      return `
        <div style="padding:8px 0; ${idx > 0 ? "border-top:1px solid #eee;" : ""}">
          <div style="font-weight:700">${name}</div>
          ${detail ? `<div style="color:#666">${detail}</div>` : ""}
          <div>매니저: ${manager}</div>
          <div>희망시간: ${time}</div>
          <div>식수: ${stop.meals}</div>
          <div>고객사: ${stop.accounts}</div>
          <div>라인업: ${lineup}</div>
        </div>
      `;
    })
    .join("");

  return `
    <div style="font-size:12px;line-height:1.5;min-width:260px;max-width:320px">
      <div style="font-weight:700;font-size:13px;margin-bottom:6px">${title}</div>
      ${itemsHtml}
    </div>
  `;
}

function routeColor(route: RouteSummary, selectedManagerId: number | null) {
  if (selectedManagerId == null) return route.manager_color || "#3367d6";
  return route.manager_id === selectedManagerId ? route.manager_color || "#3367d6" : "#c7cdd6";
}

function routeOpacity(route: RouteSummary, selectedManagerId: number | null) {
  if (selectedManagerId == null) return 0.9;
  return route.manager_id === selectedManagerId ? 1 : 0.25;
}

function groupStops(stops: StopPoint[]): StopGroup[] {
  const map = new Map<string, StopGroup>();

  stops.forEach((stop) => {
    const key = `${stop.latitude.toFixed(6)},${stop.longitude.toFixed(6)}`;
    if (!map.has(key)) {
      map.set(key, {
        key,
        latitude: stop.latitude,
        longitude: stop.longitude,
        managerColor: stop.manager_color,
        items: [],
      });
    }
    map.get(key)!.items.push(stop);
  });

  return Array.from(map.values());
}

export default function MapSection({
  stops,
  routes,
  selectedManagerId,
}: {
  stops: StopPoint[];
  routes: RouteSummary[];
  selectedManagerId: number | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const groups = useMemo(() => groupStops(stops), [stops]);

  useEffect(() => {
    let markers: any[] = [];
    let polylines: any[] = [];
    let map: any;
    let infoWindow: any;

    loadNaverMaps()
      .then(() => {
        if (!ref.current || !window.naver?.maps) return;
        const naver = window.naver;

        map = new naver.maps.Map(ref.current, {
          center: new naver.maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng),
          zoom: 11,
        });

        infoWindow = new naver.maps.InfoWindow({
          content: "",
          maxWidth: 340,
          backgroundColor: "#fff",
          borderColor: "#ddd",
          borderWidth: 1,
          anchorSize: new naver.maps.Size(12, 14),
        });

        const bounds = new naver.maps.LatLngBounds();

        groups.forEach((group) => {
          const pos = new naver.maps.LatLng(group.latitude, group.longitude);
          const extraCount = Math.max(group.items.length - 1, 0);
          const color = group.managerColor || "#3367d6";

          const marker = new naver.maps.Marker({
            map,
            position: pos,
            icon: {
              content: `
                <div style="position:relative;transform:translate(-50%, -50%);">
                  <div style="width:${extraCount > 0 ? 24 : 20}px;height:${extraCount > 0 ? 24 : 20}px;border-radius:9999px;background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.25);"></div>
                  ${extraCount > 0 ? `<div style="position:absolute;left:50%;top:50%;transform:translate(-50%, -50%);color:#fff;font-size:11px;font-weight:700;">+${extraCount}</div>` : ""}
                </div>
              `,
              anchor: new naver.maps.Point(extraCount > 0 ? 12 : 10, extraCount > 0 ? 12 : 10),
            },
            title: group.items[0]?.address_name || String(group.items[0]?.address_id),
          });

          const html = buildPopupHtml(group);
          naver.maps.Event.addListener(marker, "click", () => {
            infoWindow.setContent(html);
            infoWindow.open(map, marker);
          });

          markers.push(marker);
          bounds.extend(pos);
        });

        routes.forEach((route) => {
          const color = routeColor(route, selectedManagerId);
          const opacity = routeOpacity(route, selectedManagerId);

          if (route.completed_path?.length) {
            const path = route.completed_path.map((p) => new naver.maps.LatLng(p.lat, p.lng));
            const line = new naver.maps.Polyline({
              map,
              path,
              strokeColor: color,
              strokeOpacity: opacity,
              strokeWeight: selectedManagerId === route.manager_id ? 6 : 4,
              strokeLineCap: "round",
              strokeLineJoin: "round",
            });
            polylines.push(line);
            path.forEach((p) => bounds.extend(p));
          }

          if (route.remaining_path?.length) {
            const path = route.remaining_path.map((p) => new naver.maps.LatLng(p.lat, p.lng));
            const line = new naver.maps.Polyline({
              map,
              path,
              strokeColor: color,
              strokeOpacity: opacity * 0.9,
              strokeWeight: selectedManagerId === route.manager_id ? 6 : 4,
              strokeStyle: "shortdash",
              strokeLineCap: "round",
              strokeLineJoin: "round",
            });
            polylines.push(line);
            path.forEach((p) => bounds.extend(p));
          }
        });

        if (!bounds.isEmpty()) {
          map.fitBounds(bounds);
        }
      })
      .catch((e) => {
        console.error(e);
      });

    return () => {
      markers.forEach((m) => m.setMap(null));
      polylines.forEach((p) => p.setMap(null));
    };
  }, [groups, routes, selectedManagerId]);

  const selectedRoute =
    selectedManagerId == null
      ? null
      : routes.find((r) => r.manager_id === selectedManagerId) ?? null;

  return (
    <div>
      <h2 style={{ fontSize: 16, margin: "24px 0 8px" }}>배송 지도</h2>
      <div
        ref={ref}
        style={{
          width: "100%",
          height: 620,
          borderRadius: 12,
          border: "1px solid #e5e7eb",
          background: "#f8f9fb",
        }}
      />
      <div style={{ marginTop: 8, fontSize: 12, color: "#666", display: "grid", gap: 4 }}>
        <div>
          같은 좌표의 배송지는 마커 1개로 묶어 표시하며, 추가 건수는 <b>+N</b>으로 표시됩니다.
        </div>
        {selectedRoute ? (
          <div>
            선택 노선: {selectedRoute.manager_name ?? selectedRoute.manager_id}
            {selectedRoute.distance_m > 0 && ` · ${(selectedRoute.distance_m / 1000).toFixed(1)}km`}
            {selectedRoute.duration_ms > 0 && ` · ${Math.round(selectedRoute.duration_ms / 60000)}분`}
            {selectedRoute.origin_name ? ` · 출발지: ${selectedRoute.origin_name}` : ""}
            {` · 완료 ${selectedRoute.completed_stops} / 남은 ${selectedRoute.remaining_stops}`}
            {selectedRoute.toll_fare > 0 && ` · 예상 통행요금 ${selectedRoute.toll_fare.toLocaleString()}원`}
            {selectedRoute.fuel_price_naver > 0 && ` · NAVER 예상 유류비 ${selectedRoute.fuel_price_naver.toLocaleString()}원`}
            {selectedRoute.fuel_price_opinet && ` · 오피넷 기준 예상 유류비 ${selectedRoute.fuel_price_opinet.toLocaleString()}원`}
            {selectedRoute.source === "cache"
              ? " · 캐시"
              : selectedRoute.source === "naver"
                ? " · 새 계산"
                : selectedRoute.source === "pending"
                  ? " · 예상 경로 계산 전"
                  : " · 경로 없음"}
          </div>
        ) : (
          <div>전체 노선 표시 중</div>
        )}
      </div>
    </div>
  );
}
