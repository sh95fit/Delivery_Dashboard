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

/** 도착 순서 맵: ID(숫자/UUID 모두)를 문자열 키로 통일해 매칭 실패 방지 */
function buildOrderMap(routes: RouteSummary[]) {
  const order = new Map<string, number>();
  routes.forEach((route) => {
    const ids = [...(route.completed_stop_ids ?? []), ...(route.remaining_stop_ids ?? [])];
    ids.forEach((id, idx) => {
      const key = String(id);
      if (!order.has(key)) order.set(key, idx + 1);
    });
  });
  return order;
}

function buildPopupHtml(group: StopGroup, order?: number) {
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
        <div style="padding:8px 0; ${idx > 0 ? "border-top:1px solid #f0f0f0;" : ""}">
          <div style="font-weight:700;font-size:13px;">${name}</div>
          ${detail ? `<div style="color:#8a8f98;font-size:11px;margin-top:2px;">${detail}</div>` : ""}
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;">
            <span style="background:#f1f5f9;border-radius:4px;padding:2px 6px;font-size:11px;">매니저: ${manager}</span>
            <span style="background:#fff7e6;border-radius:4px;padding:2px 6px;font-size:11px;">${time}</span>
            <span style="background:#eef4ff;border-radius:4px;padding:2px 6px;font-size:11px;">${stop.meals}식</span>
            <span style="background:#f0fdf4;border-radius:4px;padding:2px 6px;font-size:11px;">${stop.accounts}곳</span>
          </div>
          <div style="color:#666;font-size:11px;margin-top:4px;">라인업: ${lineup}</div>
        </div>
      `;
    })
    .join("");

  return `
    <div style="position:relative;font-size:12px;line-height:1.5;min-width:260px;max-width:320px;font-family:inherit;">
      <button id="lunchlab-iw-close" style="position:absolute;top:6px;right:6px;width:24px;height:24px;border:none;background:transparent;font-size:16px;color:#98a2b3;cursor:pointer;line-height:1;" aria-label="닫기">✕</button>
      <div style="font-weight:800;font-size:14px;margin-bottom:6px;padding-right:28px;">
        ${order ? `<span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:9999px;background:#2563eb;color:#fff;font-size:11px;font-weight:700;margin-right:6px;">${order}</span>` : ""}
        ${title}
      </div>
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

/** 폴링 응답에 경로가 비어버린 매니저는 이전 정상 경로를 유지(스테일 폴백). */
function mergeWithStaleRoutes(current: RouteSummary[], previous: RouteSummary[]): RouteSummary[] {
  return current.map((route) => {
    const hasPath = (route.completed_path?.length ?? 0) >= 2 || (route.remaining_path?.length ?? 0) >= 2;
    if (hasPath) return route;

    const stale = previous.find((p) => p.manager_id === route.manager_id);
    const staleHasPath =
      stale && ((stale.completed_path?.length ?? 0) >= 2 || (stale.remaining_path?.length ?? 0) >= 2);

    if (staleHasPath) {
      return {
        ...stale!,
        completed_stops: route.completed_stops,
        remaining_stops: route.remaining_stops,
        source: "cache",
        payload: { note: "stale route kept while recalculation is in progress" },
      } as RouteSummary;
    }
    return route;
  });
}

export default function MapSection({
  stops,
  routes,
  selectedManagerId,
  onSelectManager,
  autoFitKey,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  const mapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const polylinesRef = useRef<any[]>([]);
  const originMarkerRef = useRef<any>(null);
  const infoWindowRef = useRef<any>(null);

  const hasUserInteractedRef = useRef(false);
  const lastAutoFitKeyRef = useRef<string | null>(null);
  const lastGoodRoutesRef = useRef<RouteSummary[]>([]);

  const groups = useMemo(() => groupStops(stops), [stops]);

  const effectiveRoutes = useMemo(
    () => mergeWithStaleRoutes(routes, lastGoodRoutesRef.current),
    [routes],
  );

  useEffect(() => {
    const anyPath = routes.some(
      (r) => (r.completed_path?.length ?? 0) >= 2 || (r.remaining_path?.length ?? 0) >= 2,
    );
    if (anyPath) lastGoodRoutesRef.current = routes;
  }, [routes]);

  const routeColor = (route: RouteSummary) => {
    if (selectedManagerId == null) return route.manager_color || "#3367d6";
    return route.manager_id === selectedManagerId ? route.manager_color || "#3367d6" : "#c7cdd6";
  };

  const routeOpacity = (route: RouteSummary) => {
    if (selectedManagerId == null) return 0.9;
    return route.manager_id === selectedManagerId ? 1 : 0.25;
  };

  // 1) 지도 초기화 — 마운트 시 1회
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
          borderColor: "#e5e7eb",
          borderWidth: 1,
          borderRadius: 10,
          anchorSize: new naver.maps.Size(12, 14),
        });

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

  // 2) 출발지 핀 — 백엔드가 내려준 origin 좌표 사용 (배치 이음선이 아니라 진짜 출발지)
  useEffect(() => {
    const naver = window.naver;
    const map = mapRef.current;
    if (!naver?.maps || !map) return;

    const withOrigin = effectiveRoutes.find(
      (r) =>
        typeof r.origin_latitude === "number" &&
        Number.isFinite(r.origin_latitude) &&
        typeof r.origin_longitude === "number" &&
        Number.isFinite(r.origin_longitude),
    );

    const origin = withOrigin
      ? { lat: withOrigin.origin_latitude as number, lng: withOrigin.origin_longitude as number }
      : null;

    if (!origin || !Number.isFinite(origin.lat) || !Number.isFinite(origin.lng)) {
      if (originMarkerRef.current) {
        originMarkerRef.current.setMap(null);
        originMarkerRef.current = null;
      }
      return;
    }

    if (!originMarkerRef.current) {
      originMarkerRef.current = new naver.maps.Marker({
        map,
        position: new naver.maps.LatLng(origin.lat, origin.lng),
        icon: {
          content: `
            <div style="position:relative;transform:translate(-50%, -100%);">
              <div style="width:38px;height:38px;border-radius:9999px 9999px 9999px 4px;background:#111827;border:3px solid #fff;box-shadow:0 3px 10px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;font-size:17px;">🏠</div>
              <div style="position:absolute;left:50%;top:40px;transform:translateX(-50%);background:#111827;color:#fff;font-size:10px;font-weight:800;padding:2px 7px;border-radius:4px;white-space:nowrap;">출발</div>
            </div>
          `,
          anchor: new naver.maps.Point(19, 38),
        },
        zIndex: 100,
      });
    } else {
      originMarkerRef.current.setPosition(new naver.maps.LatLng(origin.lat, origin.lng));
    }
  }, [effectiveRoutes]);

  // 3) 마커/폴리라인 — 데이터 변경 시 내용만 교체
  useEffect(() => {
    const naver = window.naver;
    const map = mapRef.current;
    if (!naver?.maps || !map) return;

    markersRef.current.forEach((m) => m.setMap(null));
    polylinesRef.current.forEach((p) => p.setMap(null));
    markersRef.current = [];
    polylinesRef.current = [];

    const bounds = new naver.maps.LatLngBounds();
    // NAVER LatLngBounds에는 isEmpty()가 없다 -> 확장 여부를 직접 기록
    let hasBoundsPoints = false;

    const orderMap = buildOrderMap(effectiveRoutes);

    groups.forEach((group) => {
      const pos = new naver.maps.LatLng(group.latitude, group.longitude);
      const extraCount = Math.max(group.items.length - 1, 0);
      const color = group.managerColor || "#3367d6";

      const orderNo = (() => {
        for (const item of group.items) {
          const hit =
            orderMap.get(String(item.delivery_id ?? "")) ??
            orderMap.get(String(item.address_id ?? ""));
          if (hit != null) return hit;
        }
        return undefined;
      })();

      const size = 26;
      const marker = new naver.maps.Marker({
        map,
        position: pos,
        icon: {
          content: `
            <div style="position:relative;transform:translate(-50%, -50%);">
              <div style="width:${size}px;height:${size}px;border-radius:9999px;background:${color};border:2.5px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3);display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:800;">
                ${orderNo ?? ""}
              </div>
              ${extraCount > 0 ? `
                <div style="position:absolute;right:-14px;top:-8px;min-width:20px;height:18px;padding:0 5px;border-radius:9px;background:#111827;color:#fff;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 3px rgba(0,0,0,.35);">+${extraCount}</div>
              ` : ""}
            </div>
          `,
          anchor: new naver.maps.Point(size / 2, size / 2),
        },
        title: group.items[0]?.address_name || String(group.items[0]?.address_id),
      });

      const html = buildPopupHtml(group, orderNo);
      naver.maps.Event.addListener(marker, "click", () => {
        infoWindowRef.current?.setContent(html);
        infoWindowRef.current?.open(map, marker);

        const closeBtn = document.getElementById("lunchlab-iw-close");
        if (closeBtn) {
          closeBtn.addEventListener("click", () => {
            infoWindowRef.current?.close();
          });
        }

        const managerId = group.items[0]?.manager_id;
        if (onSelectManager && typeof managerId === "number") {
          onSelectManager(managerId);
        }
      });

      markersRef.current.push(marker);
      bounds.extend(pos);
      hasBoundsPoints = true;
    });

    effectiveRoutes.forEach((route) => {
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
        path.forEach((p) => bounds.extend(p));
        hasBoundsPoints = true;
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
        path.forEach((p) => bounds.extend(p));
        hasBoundsPoints = true;
      }
    });

    if (lastAutoFitKeyRef.current !== autoFitKey && !hasUserInteractedRef.current) {
      if (hasBoundsPoints) {
        map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
      }
      lastAutoFitKeyRef.current = autoFitKey;
    }
  }, [groups, effectiveRoutes, selectedManagerId, autoFitKey, onSelectManager]);

  const refitNow = () => {
    const naver = window.naver;
    const map = mapRef.current;
    if (!naver?.maps || !map) return;

    const bounds = new naver.maps.LatLngBounds();

    groups.forEach((group) => {
      bounds.extend(new naver.maps.LatLng(group.latitude, group.longitude));
    });
    effectiveRoutes.forEach((route) => {
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

    if (groups.length > 0 || effectiveRoutes.length > 0) {
      map.fitBounds(bounds, { top: 40, right: 40, bottom: 40, left: 40 });
    } else {
      map.setCenter(new naver.maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng));
      map.setZoom(11);
    }
  };

  const selectedRoute =
    selectedManagerId == null
      ? null
      : effectiveRoutes.find((r) => r.manager_id === selectedManagerId) ?? null;

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
          마커 숫자는 도착 순서 · 확대/이동 중에는 갱신돼도 화면이 유지됩니다
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
          같은 좌표 배송지는 마커 1개로 묶어 표시하며, 추가 건수는 마커 옆 <b>+N</b> 칩으로 표시됩니다.
        </div>
        {selectedRoute ? (
          <div>
            선택 노선: {selectedRoute.manager_name ?? selectedRoute.manager_id}
            {selectedRoute.distance_m > 0 && ` · ${(selectedRoute.distance_m / 1000).toFixed(1)}km`}
            {selectedRoute.duration_ms > 0 && ` · ${Math.round(selectedRoute.duration_ms / 60000)}분`}
            {selectedRoute.origin_name ? ` · 출발지: ${selectedRoute.origin_name}` : ""}
            {` · 완료 ${selectedRoute.completed_stops} / 남은 ${selectedRoute.remaining_stops}`}
            {selectedRoute.toll_fare > 0 && ` · 예상 통행요금 ${selectedRoute.toll_fare.toLocaleString()}원`}
            {typeof selectedRoute.fuel_price_naver === "number" && selectedRoute.fuel_price_naver > 0 && ` · NAVER 예상 유류비 ${selectedRoute.fuel_price_naver.toLocaleString()}원`}
            {typeof selectedRoute.fuel_price_opinet === "number" && selectedRoute.fuel_price_opinet > 0 && ` · 오피넷 기준 예상 유류비 ${selectedRoute.fuel_price_opinet.toLocaleString()}원`}
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
