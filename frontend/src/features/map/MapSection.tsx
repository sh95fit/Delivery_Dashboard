import { useEffect, useRef } from "react";
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

export default function MapSection({ stops }: { stops: StopPoint[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let markers: any[] = [];
    let map: any;

    loadGoogleMaps()
      .then(() => {
        if (!ref.current || !window.google) return;

        map = new window.google.maps.Map(ref.current, {
          center: DEFAULT_CENTER,
          zoom: 11,
        });

        const bounds = new window.google.maps.LatLngBounds();

        stops.forEach((stop) => {
          const pos = { lat: stop.latitude, lng: stop.longitude };
          const marker = new window.google.maps.Marker({
            map,
            position: pos,
            title: stop.address_name || String(stop.address_id),
            icon: stop.manager_color
              ? {
                  path: window.google.maps.SymbolPath.CIRCLE,
                  scale: 7,
                  fillColor: stop.manager_color,
                  fillOpacity: 1,
                  strokeColor: "#ffffff",
                  strokeWeight: 1,
                }
              : undefined,
          });

          const info = new window.google.maps.InfoWindow({
            content: `
              <div style="font-size:12px;line-height:1.5;min-width:220px">
                <div style="font-weight:700;margin-bottom:4px">${stop.address_name ?? stop.address_id}</div>
                <div>매니저: ${stop.manager_name ?? "미배정"}</div>
                <div>희망시간: ${stop.delivery_time ?? "없음"}</div>
                <div>식수: ${stop.meals}</div>
                <div>고객사: ${stop.accounts}</div>
                <div>라인업: ${lineupText(stop) || "없음"}</div>
              </div>
            `,
          });

          marker.addListener("click", () => info.open({ map, anchor: marker }));
          markers.push(marker);
          bounds.extend(pos);
        });

        if (stops.length > 0) map.fitBounds(bounds);
      })
      .catch((e) => {
        console.error(e);
      });

    return () => {
      markers.forEach((m) => m.setMap(null));
      markers = [];
    };
  }, [stops]);

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
        매니저 색상 핀을 클릭하면 배송지 상세 정보가 표시됩니다.
      </p>
    </div>
  );
}
