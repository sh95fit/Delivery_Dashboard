import { useEffect, useMemo, useRef } from "react";
import type { RouteSummary, StopPoint } from "@/api/types";

const DEFAULT_CENTER = { lat: 37.5665, lng: 126.978 };

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

type Props = {
  stops: StopPoint[];
  routes: RouteSummary[];
  selectedManagerId: number | null;
  onSelectManager?: (managerId: number | null) => void;
  /** 날짜/담당자 변경 시에만 바뀌는 키. 이 키가 바뀔 때만 지도를 자동 재정렬한다. */
  autoFitKey: string;
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

    const clientId = import.meta.env.VITE_NAVER_MAP_CLIENT_ID;
    if (!clientId) {
      reject(new Error("VITE_NAVER_MAP_CLIENT_ID가 없습니다"));
      return;
    }

    const script = document.createElement("script");
    script.id = "naver-maps-script";
    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}`;
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

function groupStops(stops: StopPoint[]): StopGroup[] {
  const map = new Map<string, StopGroup>();

  stops.forEach((stop) => {
    if (typeof stop.latitude !== "number" || typeof stop.longitude !== "number") return;
    if (!Number.isFinite(stop.latitude) || !Number.isFinite(stop.longitude)) return;

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
  onSelectManager,
  autoFitKey,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  // 지도는 한 번만 만들고 재사용한다
  const mapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const polylinesRef = useRef<any[]>([]);
  const infoWindowRef = useRef<any>(null);

  // 폴링 UX: 사용자가 확대/이동했으면 자동 재정렬 금지
  const hasUserInteractedRef = useRef(false);
  const lastAutoFitKeyRef = useRef<string | null>(null);

  const groups = useMemo(() => groupStops(stops), [stops]);

  const routeColor = (route: RouteSummary) => {
    if (selectedManagerId == null) return route.manager_color || "#3367d6";
    return route.manager_id === selectedManagerId ? route.manager_color || "#3367d6" : "#c7cdd6";
  };

  const routeOpacity = (route: RouteSummary) => {
    if (selectedManagerId == null) return 0.9;
    return route.manager_id === selectedManagerId ? 1 : 0.25;
  };

  // 1) 지도 초기화 — 컴포넌트 마운트 시 1회만
  useEffect(() => {
    let cancelled = false;

    loadNaverMaps()
      .then(() => {
        if (cancelled || !containerRef.current || mapRef.current || !window.naver?.maps) return;
        const naver = window.naver;

        mapRef.current = new naver.maps.Map(containerRef.current, {
          center: new naver.maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng),
          zoom: 11,
        });

        infoWindowRef.current = new naver.maps.InfoWindow({
          content: "",
          maxWidth: 340,
          backgroundColor: "#fff",
          borderColor: "#ddd",
          borderWidth: 1,
          anchorSize: new naver.maps.Size(12, 14),
        });

        // 사용자가 직접 움직이면 자동 재정렬을 멈춘다
        naver.maps.Event.addListener(mapRef.current, "dragend", () => {
          hasUserInteractedRef.current = true;
        });
        naver.maps.Event.addListener(mapRef.current, "zoom_changed", () => {
          hasUserInteractedRef.current = true;
        });
      })
      .catch((e) => {
        console.error(e);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // 2) 마커/폴리라인 그리기 — 데이터가 바뀔 때 지도 객체는 유지한 채 내용만 교체
  useEffect(() => {
    const naver = window.naver;
    const map = mapRef.current;
    if (!naver?.maps || !map) return;

    // 이전 레이어 정리
    markersRef.current.forEach((m) => m.setMap(null));
    polylinesRef.current.forEach((p) => p.setMap(null));
    markersRef.current = [];
    polylinesRef.current = [];

    const bounds = new naver.maps.LatLngBounds();

    // 마커
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
        infoWindowRef.current?.setContent(html);
        infoWindowRef.current?.open(map, marker);

        const managerId = group.items[0]?.manager_id;
        if (onSelectManager && typeof managerId === "number") {
          onSelectManager(managerId);
        }
      });

      markersRef.current.push(marker);
      bounds.extend(pos);
    });

    // 경로선
    routes.forEach((route) => {
      const color = routeColor(route);
      const opacity = routeOpacity(route);

      const completed = (route.completed_path ?? []).filter(
        (p) => p && Number.isFinite(p.lat) && Number.isFinite(p.lng),
      );
      const remaining = (route.remaining_path ?? []).filter(
        (p) => p && Number.isFinite(p.lat) && Number.isFinite(p.lng),
      );

      if (completed.length >= 2) {
        const path = completed.map((p) => new naver.maps.LatLng(p.lat, p.lng));
        const line = new naver.maps.Polyline({
          map,
          path,
          strokeColor: color,
          strokeOpacity: opacity,
          strokeWeight: selectedManagerId === route.manager_id ? 6 : 4,
          strokeLineCap: "round",
          strokeLineJoin: "round",
        });
        polylinesRef.current.push(line);
        path.forEach((p) => bounds.extend(new naver.maps.LatLng(p.lat, p.lng)));
      }

      if (remaining.length >= 2) {
        const path = remaining.map((p) => new naver.maps.LatLng(p.lat, p.lng));
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
        polylinesRef.current.push(line);
        path.forEach((p) => bounds.extend(new naver.maps.LatLng(p.lat, p.lng)));
      }
    });

    // 자동 재정렬은 autoFitKey가 바뀔 때만.
    // 폴링은 autoFitKey를 바꾸지 않으므로, 여기서 지도 시점이 초기화되지 않는다.
    if (lastAutoFitKeyRef.current !== autoFitKey && !hasUserInteractedRef.current) {
      if (!bounds.isEmpty()) {
        map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
      }
      lastAutoFitKeyRef.current = autoFitKey;
    }
  }, [groups, routes, selectedManagerId, autoFitKey, onSelectManager]);

  // 수동 재정렬 ("전체 보기" 버튼)
  const refitNow = () => {
    const naver = window.naver;
    const map = mapRef.current;
    if (!naver?.maps || !map) return;

    const bounds = new naver.maps.LatLngBounds();

    groups.forEach((group) => {
      bounds.extend(new naver.maps.LatLng(group.latitude, group.longitude));
    });
    routes.forEach((route) => {
      (route.completed_path ?? []).forEach((p) => {
        if (p && Number.isFinite(p.lat) && Number.isFinite(p.lng)) {
          bounds.extend(new naver.maps.LatLng(p.lat, p.lng));
        }
      });
      (route.remaining_path ?? []).forEach((p) => {
        if (p && Number.isFinite(p.lat) && Number.isFinite(p.lng)) {
          bounds.extend(new naver.maps.LatLng(p.lat, p.lng));
        }
      });
    });

    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
    } else {
      map.setCenter(new naver.maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng));
      map.setZoom(11);
    }
  };

  const selectedRoute =
    selectedManagerId == null
      ? null
      : routes.find((r) => r.manager_id === selectedManagerId) ?? null;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "24px 0 8px" }}>
        <h2 style={{ fontSize: 16, margin: 0 }}>배송 지도</h2>
        <button
          type="button"
          onClick={() => {
            hasUserInteractedRef.current = false;
            refitNow();
          }}
          style={{
            fontSize: 12,
            padding: "4px 10px",
            borderRadius: 6,
            border: "1px solid #d0d7e2",
            background: "#fff",
            cursor: "pointer",
          }}
        >
          전체 보기
        </button>
        <span style={{ fontSize: 12, color: "#888" }}>
          확대/이동 중에는 갱신돼도 화면이 유지됩니다
        </span>
      </div>
      <div
        ref={containerRef}
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
