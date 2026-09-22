import { useEffect, useMemo, useRef } from "react";
import type { StopPoint } from "@/api/types";

const DEFAULT_CENTER = { lat: 37.5665, lng: 126.9780 };

declare global {
  interface Window {
    google?: any;
  }
}

function lineupText(stop: StopPoint) {
  const parts = Object.values(stop.lineups)
    .filter((x) => x.qty > 0)
    .map((x) => `${x.name} ${x.qty}`);
  return parts.join(" / ");
}

function loadGoogleMaps(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.google?.maps) return resolve();

    const existing = document.getElementById("google-maps-script") as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("Google Maps 스크립트 로드 실패")));
      return;
    }

    const key = import.meta.env.VITE_MAPS_API_KEY;
    if (!key) {
      reject(new Error("VITE_MAPS_API_KEY가 없습니다"));
      return;
    }

    const script = document.createElement("script");
    script.id = "google-maps-script";
    script.src = `https://maps.googleapis.com/maps/api/js?key=${key}`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Google Maps 스크립트 로드 실패"));
    document.head.appendChild(script);
  });
}

type StopGroup = {
  key: string;
  latitude: number;
  longitude: number;
  managerColor?: string | null;
  items: StopPoint[];
};

function buildPopupHtml(group: StopGroup) {
  const title = group.items[0]?.address_name ?? String(group.items[0]?.address_id ?? "배송지");
  const total = group.items.length;

  const itemsHtml = group.items
    .sort((a, b) => {
      const at = a.delivery_time ?? "99:99";
      const bt = b.delivery_time ?? "99:99";
      if (at !== bt) return at.localeCompare(bt);
      return (a.detail_address ?? "").localeCompare(b.detail_address ?? "");
    })
    .map((stop, idx) => {
      const detail = stop.detail_address?.trim() || "상세주소 없음";
      return `
        <div style="padding:8px 0; ${idx > 0 ? "border-top:1px solid #eee;" : ""}">
          <div style="font-weight:700">${detail}</div>
          <div>매니저: ${stop.manager_name ?? "미배정"}</div>
          <div>희망시간: ${stop.delivery_time ?? "없음"}</div>
          <div>식수: ${stop.meals}</div>
          <div>고객사: ${stop.accounts}</div>
          <div>라인업: ${lineupText(stop) || "없음"}</div>
        </div>
      `;
    })
    .join("");

  return `
    <div style="font-size:12px;line-height:1.5;min-width:260px;max-width:320px">
      <div style="font-weight:700;font-size:13px;margin-bottom:6px">${title} ${total > 1 ? `(총 ${total}건)` : ""}</div>
      ${itemsHtml}
    </div>
  `;
}

export default function MapSection({ stops }: { stops: StopPoint[] }) {
  const ref = useRef<HTMLDivElement>(null);

  const groups = useMemo<StopGroup[]>(() => {
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
  }, [stops]);

  useEffect(() => {
    let markers: any[] = [];
    let map: any;
    let infoWindow: any;

    loadGoogleMaps()
      .then(() => {
        if (!ref.current || !window.google) return;

        map = new window.google.maps.Map(ref.current, {
          center: DEFAULT_CENTER,
          zoom: 11,
        });

        infoWindow = new window.google.maps.InfoWindow();
        const bounds = new window.google.maps.LatLngBounds();

        groups.forEach((group) => {
          const pos = { lat: group.latitude, lng: group.longitude };
          const extraCount = Math.max(group.items.length - 1, 0);

          const marker = new window.google.maps.Marker({
            map,
            position: pos,
            title: group.items[0]?.address_name || String(group.items[0]?.address_id),
            label: extraCount > 0
              ? {
                  text: `+${extraCount}`,
                  color: "#ffffff",
                  fontSize: "11px",
                  fontWeight: "700",
                }
              : undefined,
            icon: {
              path: window.google.maps.SymbolPath.CIRCLE,
              scale: extraCount > 0 ? 12 : 10,
              fillColor: group.managerColor || "#3367d6",
              fillOpacity: 1,
              strokeColor: "#ffffff",
              strokeWeight: 1.5,
            },
          });

          const html = buildPopupHtml(group);
          marker.addListener("click", () => {
            infoWindow.setContent(html);
            infoWindow.open({ map, anchor: marker });
          });

          markers.push(marker);
          bounds.extend(pos);
        });

        if (groups.length > 0) {
          map.fitBounds(bounds);
        }
      })
      .catch((e) => {
        console.error(e);
      });

    return () => {
      markers.forEach((m) => m.setMap(null));
      markers = [];
    };
  }, [groups]);

  return (
    <div>
      <h2 style={{ fontSize: 16, margin: "24px 0 8px" }}>배송 지도</h2>
      <div
        ref={ref}
        style={{
          width: "100%",
          height: 460,
          borderRadius: 12,
          border: "1px solid #e5e7eb",
          background: "#f8f9fb",
        }}
      />
      <p style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
        같은 좌표의 배송지는 마커 1개로 묶어 표시하며, 추가 건수는 <b>+N</b> 으로 표시됩니다.
      </p>
    </div>
  );
}
