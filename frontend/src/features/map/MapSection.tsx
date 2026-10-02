import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import type { RouteSummary, StatusState, StopPoint } from "@/api/types";
import { num, won } from "@/lib/format";

const DEFAULT_CENTER = { lat: 37.5665, lng: 126.978 };
const FIT_MARGIN = { top: 56, right: 56, bottom: 56, left: 56 };
const FALLBACK_COLOR = "#2563eb";
const UNASSIGNED_COLOR = "#6b7280";
const DIM_LINE = "#9ca3af";
const LIST_KEY = "ll.map.list";

declare global {
  interface Window {
    naver?: any;
  }
}

type Phase = "preview" | "live" | "result";
type Pt = { lat: number; lng: number };
type StopGroup = { key: string; latitude: number; longitude: number; items: StopPoint[] };
type Entry = { marker: any; group: StopGroup };
type Row = {
  id: number; name: string; color: string; stops: number; done: number; meals: number;
  km: number; min: number; hasLine: boolean; hasOrder: boolean;
};
type SortKey = "name" | "todo" | "stops";

type Props = {
  stops: StopPoint[];
  /** 전체 노선 (선택 노선만 거르지 말 것 — 흐림 처리·번호 계산에 전체가 필요) */
  routes: RouteSummary[];
  state?: StatusState;
  selectedManagerId: number | null;
  onSelectManager?: (managerId: number | null) => void;
  /** 날짜/선택 노선이 바뀔 때만 바뀌는 키. 바뀌면 화면을 자동으로 맞춘다 (폴링 갱신 때는 유지) */
  autoFitKey: string;
  loading?: boolean;
  routesLoading?: boolean;
};

/* ---------- 유틸 ---------- */
const esc = (v: unknown) =>
  String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const safeColor = (c?: string | null) => (c && /^#[0-9a-fA-F]{3,8}$/.test(c) ? c : FALLBACK_COLOR);
const okPt = (p: any): p is Pt => Boolean(p) && Number.isFinite(p.lat) && Number.isFinite(p.lng);
const phaseOf = (s?: StatusState): Phase => (s === "LIVE" ? "live" : s === "RESULT" ? "result" : "preview");
const isPreviewStop = (s: StopPoint) => String(s.delivery_id).startsWith("preview-");
const hasLine = (r?: RouteSummary) =>
  Boolean(r) && ((r!.completed_path?.length ?? 0) >= 2 || (r!.remaining_path?.length ?? 0) >= 2);

const hhmm = (iso?: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Seoul" });
};

const fmtMin = (m: number) => {
  const r = Math.round(m);
  return r >= 60 ? `${Math.floor(r / 60)}시간 ${r % 60}분` : `${r}분`;
};

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
    if (!clientId) return reject(new Error("VITE_NAVER_MAP_CLIENT_ID가 없습니다"));
    const script = document.createElement("script");
    script.id = "naver-maps-script";
    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${clientId}`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("NAVER Maps 스크립트 로드 실패"));
    document.head.appendChild(script);
  });
}

/* ---------- 번호: 매니저별 · 배송건별 ---------- */
function buildOrderMap(routes: RouteSummary[]) {
  const order = new Map<string, number>();
  for (const r of routes) {
    const ids = [...(r.completed_stop_ids ?? []), ...(r.remaining_stop_ids ?? [])];
    ids.forEach((id, i) => {
      const k = `${r.manager_id}:${id}`;
      if (!order.has(k)) order.set(k, i + 1);
    });
  }
  return order;
}

function stopNo(s: StopPoint, order: Map<string, number>) {
  if (s.manager_id == null) return undefined;
  return (
    order.get(`${s.manager_id}:${s.delivery_id}`) ??
    (s.address_id != null ? order.get(`${s.manager_id}:${s.address_id}`) : undefined)
  );
}

const visibleItems = (g: StopGroup, sel: number | null) =>
  sel == null ? g.items : g.items.filter((x) => x.manager_id === sel);

function groupNos(g: StopGroup, order: Map<string, number>, sel: number | null) {
  const set = new Set<number>();
  for (const it of visibleItems(g, sel)) {
    const n = stopNo(it, order);
    if (n != null) set.add(n);
  }
  return [...set].sort((a, b) => a - b);
}

/** [5] → "5", [5,6,7] → "5-7", [5,9] → "5,9", [3,5,9] → "3,5…" */
function noLabel(nums: number[]) {
  if (nums.length === 0) return "";
  if (nums.length === 1) return String(nums[0]);
  const consecutive = nums.every((n, i) => i === 0 || n === nums[i - 1] + 1);
  if (consecutive) return `${nums[0]}-${nums[nums.length - 1]}`;
  return nums.length === 2 ? `${nums[0]},${nums[1]}` : `${nums[0]},${nums[1]}…`;
}

function groupColor(g: StopGroup, sel: number | null) {
  const pick = (sel != null && g.items.find((x) => x.manager_id === sel)) || g.items[0];
  if (!pick || pick.manager_id == null) return UNASSIGNED_COLOR;
  return safeColor(pick.manager_color);
}

function groupStops(stops: StopPoint[]): StopGroup[] {
  const map = new Map<string, StopGroup>();
  for (const s of stops) {
    if (typeof s.latitude !== "number" || typeof s.longitude !== "number") continue;
    if (!Number.isFinite(s.latitude) || !Number.isFinite(s.longitude)) continue;
    const key = `${s.latitude.toFixed(6)},${s.longitude.toFixed(6)}`;
    if (!map.has(key)) map.set(key, { key, latitude: s.latitude, longitude: s.longitude, items: [] });
    map.get(key)!.items.push(s);
  }
  return Array.from(map.values());
}

function mergeWithStaleRoutes(current: RouteSummary[], previous: RouteSummary[]): RouteSummary[] {
  return current.map((route) => {
    if (hasLine(route)) return route;
    const stale = previous.find((p) => p.manager_id === route.manager_id);
    if (!hasLine(stale)) return route;
    return {
      ...stale!,
      completed_stops: route.completed_stops,
      remaining_stops: route.remaining_stops,
      completed_stop_ids: route.completed_stop_ids ?? stale!.completed_stop_ids,
      remaining_stop_ids: route.remaining_stop_ids ?? stale!.remaining_stop_ids,
      source: "cache",
    } as RouteSummary;
  });
}

/* ---------- 마커 ---------- */
type MkState = "done" | "todo" | "miss" | "plan";

/** 바탕 = 매니저 색(노선), 링 = 상태. 같은 위치 여러 건은 하나라도 미배송이면 링 표시 */
function markerState(vis: StopPoint[], phase: Phase): MkState {
  if (phase === "preview" || vis.every(isPreviewStop)) return "plan";
  if (vis.every((x) => x.delivered_at)) return "done";
  return phase === "live" ? "todo" : "miss";
}

function markerStyle(naver: any, g: StopGroup, order: Map<string, number>, sel: number | null, phase: Phase) {
  const focus = sel != null && g.items.some((x) => x.manager_id === sel);
  const dim = sel != null && !focus;
  const vis = visibleItems(g, sel);
  const nums = dim ? [] : groupNos(g, order, sel);
  const color = groupColor(g, sel);
  const st: MkState | null = dim ? null : markerState(vis, phase);
  const open = st === "todo" || st === "miss";
  const extra = !dim && nums.length <= 1 && vis.length > 1 ? vis.length - 1 : 0;
  const cls = ["mk", focus && "focus", dim && "dim"].filter(Boolean).join(" ");
  const numCls = st ? `mk-num st-${st}` : "mk-num";
  const style = dim ? "" : `background:${color}`;
  const content =
    `<div class="${cls}"><span class="${numCls}" style="${style}">${dim ? "" : esc(noLabel(nums))}` +
    `${extra > 0 ? `<span class="mk-more">+${extra}</span>` : ""}` +
    `${st === "miss" ? `<span class="mk-flag">!</span>` : ""}</span></div>`;
  const zIndex = dim ? 10 : (focus ? 300 : 100) + (open ? 20 : 0);
  return { icon: { content, anchor: new naver.maps.Point(16, 16) }, zIndex };
}

/* ---------- 정보창 ---------- */
function statusChip(s: StopPoint, phase: Phase) {
  if (phase === "preview" || isPreviewStop(s)) return `<span class="chip chip-warn">예상</span>`;
  if (s.delivered_at) return `<span class="chip chip-ok">완료 ${esc(hhmm(s.delivered_at))}</span>`;
  return phase === "live"
    ? `<span class="chip chip-caution">배송전</span>`
    : `<span class="chip chip-danger">미완료</span>`;
}

function itemHtml(s: StopPoint, no: number | undefined, phase: Phase, multi: boolean, multiMgr: boolean) {
  const meals =
    (s.dinner_meals ?? 0) > 0
      ? `${num(s.meals)}식 (중식 ${num(s.lunch_meals ?? 0)} · 석식 ${num(s.dinner_meals)})`
      : `${num(s.meals)}식`;
  const lineups =
    Object.values(s.lineups ?? {})
      .filter((x) => x.qty > 0)
      .map((x) => `${esc(x.name)} ${num(x.qty)}`)
      .join(" · ") || "-";
  const rows: Array<[string, string]> = [
    ["배송시간", esc(s.delivery_time ?? "-")],
    ...(multiMgr ? ([["매니저", esc(s.manager_name ?? "미배정")]] as Array<[string, string]>) : []),
    ["식수", meals],
    ["고객사", `${num(s.accounts)}곳`],
    ["매출", esc(won(s.net_revenue ?? 0))],
    ["라인업", lineups],
  ];
  const name = s.address_name?.trim() || `주소ID ${s.address_id}`;
  const color = s.manager_id == null ? UNASSIGNED_COLOR : safeColor(s.manager_color);
  const badge = multi && no != null ? `<span class="iw-no iw-no-sm" style="background:${color}">${no}</span>` : "";
  return `<div class="iw-item">
    ${multi ? `<div class="iw-name">${badge}${esc(name)}</div>` : ""}
    ${s.detail_address?.trim() ? `<div class="iw-detail">${esc(s.detail_address)}</div>` : ""}
    <div class="iw-chips">${statusChip(s, phase)}${s.is_internal ? `<span class="chip chip-internal">직원식</span>` : ""}</div>
    <dl class="iw-grid">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
  </div>`;
}

function popupEl(
  g: StopGroup, order: Map<string, number>, sel: number | null, phase: Phase,
  onClose: () => void, onFocus: (id: number) => void,
) {
  const items = g.items
    .map((s) => ({ s, no: stopNo(s, order) }))
    .sort((a, b) => {
      if (a.no != null && b.no != null && a.no !== b.no) return a.no - b.no;
      if ((a.no == null) !== (b.no == null)) return a.no == null ? 1 : -1;
      return (a.s.delivery_time ?? "99:99").localeCompare(b.s.delivery_time ?? "99:99");
    });
  const multi = items.length > 1;
  const multiMgr = new Set(items.map((x) => x.s.manager_id ?? null)).size > 1;
  const first = items[0].s;
  const color = groupColor(g, sel);
  const label = noLabel(groupNos(g, order, null));
  const title = multi ? `같은 위치 ${items.length}곳` : first.address_name?.trim() || `주소ID ${first.address_id}`;
  const mgr = multiMgr ? "매니저 여러 명" : first.manager_name ?? "미배정";
  const focusId = !multiMgr && typeof first.manager_id === "number" && first.manager_id !== sel ? first.manager_id : null;

  const el = document.createElement("div");
  el.className = "iw";
  el.innerHTML = `
    <div class="iw-head">
      ${label ? `<span class="iw-no" style="background:${color}">${esc(label)}</span>` : ""}
      <div class="iw-title" title="${esc(title)}">${esc(title)}</div>
      <button type="button" class="iw-close" aria-label="닫기">✕</button>
    </div>
    <div class="iw-sub"><span class="dot" style="background:${color}"></span>${esc(mgr)}</div>
    <div class="iw-body">${items.map((x) => itemHtml(x.s, x.no, phase, multi, multiMgr)).join("")}</div>
    ${focusId != null ? `<div class="iw-foot"><button type="button" class="btn btn-sm btn-primary iw-focus">이 노선만 보기</button></div>` : ""}
  `;
  el.querySelector(".iw-close")?.addEventListener("click", onClose);
  el.querySelector(".iw-focus")?.addEventListener("click", () => onFocus(focusId!));
  ["click", "mousedown", "dblclick", "touchstart", "wheel"].forEach((t) =>
    el.addEventListener(t, (e) => e.stopPropagation()),
  );
  return el;
}

/* ---------- 컴포넌트 ---------- */
export default function MapSection({
  stops, routes, state, selectedManagerId, onSelectManager, autoFitKey, loading = false, routesLoading = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const infoRef = useRef<any>(null);
  const entriesRef = useRef<Entry[]>([]);
  const linesRef = useRef<any[]>([]);
  const originRef = useRef<any>(null);
  const openKeyRef = useRef<string | null>(null);
  const fitKeyRef = useRef<string | null>(null);
  const overlayClickAt = useRef(0);
  const lastGoodRoutesRef = useRef<RouteSummary[]>([]);
  const [ready, setReady] = useState(false);
  const [built, setBuilt] = useState(0);
  const [mapError, setMapError] = useState("");
  const [listOpen, setListOpen] = useState(() => {
    try { return localStorage.getItem(LIST_KEY) !== "0"; } catch { return true; }
  });
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>(state === "LIVE" ? "todo" : "name");

  const phase = phaseOf(state);
  const select = onSelectManager ?? (() => {});
  const groups = useMemo(() => groupStops(stops), [stops]);
  const effectiveRoutes = useMemo(() => mergeWithStaleRoutes(routes, lastGoodRoutesRef.current), [routes]);
  const order = useMemo(() => buildOrderMap(effectiveRoutes), [effectiveRoutes]);

  useEffect(() => {
    if (routes.some(hasLine)) lastGoodRoutesRef.current = routes;
  }, [routes]);

  useEffect(() => {
    try { localStorage.setItem(LIST_KEY, listOpen ? "1" : "0"); } catch { /* 무시 */ }
  }, [listOpen]);

  const live = useRef({ sel: selectedManagerId, order, select, phase });
  live.current = { sel: selectedManagerId, order, select, phase };

  /* 노선 목록 데이터 */
  const rows = useMemo<Row[]>(() => {
    const m = new Map<number, Row>();
    for (const s of stops) {
      if (s.manager_id == null) continue;
      const it = m.get(s.manager_id) ?? {
        id: s.manager_id, name: s.manager_name ?? String(s.manager_id), color: safeColor(s.manager_color),
        stops: 0, done: 0, meals: 0, km: 0, min: 0, hasLine: false, hasOrder: false,
      };
      it.stops += 1;
      it.meals += s.meals ?? 0;
      if (s.delivered_at) it.done += 1;
      m.set(s.manager_id, it);
    }
    for (const r of effectiveRoutes) {
      const it = m.get(r.manager_id);
      if (!it) continue;
      it.km = (r.distance_m ?? 0) / 1000;
      it.min = (r.duration_ms ?? 0) / 60000;
      it.hasLine = hasLine(r);
      it.hasOrder = (r.completed_stop_ids?.length ?? 0) + (r.remaining_stop_ids?.length ?? 0) > 0;
    }
    return [...m.values()];
  }, [stops, effectiveRoutes]);

  const listRows = useMemo(() => {
    const key = q.trim().toLowerCase();
    const filtered = key ? rows.filter((r) => r.name.toLowerCase().includes(key)) : rows;
    const byName = (a: Row, b: Row) => a.name.localeCompare(b.name, "ko", { numeric: true });
    return filtered.slice().sort((a, b) => {
      if (sort === "todo") return b.stops - b.done - (a.stops - a.done) || byName(a, b);
      if (sort === "stops") return b.stops - a.stops || byName(a, b);
      return byName(a, b);
    });
  }, [rows, q, sort]);

  const totals = useMemo(
    () => ({
      stops: stops.length,
      done: stops.filter((s) => s.delivered_at).length,
      unassigned: stops.filter((s) => s.manager_id == null).length,
    }),
    [stops],
  );

  function step(d: 1 | -1) {
    if (listRows.length === 0) return;
    const i = listRows.findIndex((r) => r.id === selectedManagerId);
    const next = i < 0 ? (d === 1 ? 0 : listRows.length - 1) : (i + d + listRows.length) % listRows.length;
    select(listRows[next].id);
  }

  function onListKey(e: KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); step(-1); }
    else if (e.key === "Escape") { e.preventDefault(); select(null); }
  }

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-id="${selectedManagerId ?? "all"}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedManagerId, listOpen]);

  /* 지도 */
  function closeInfo() {
    infoRef.current?.close();
    openKeyRef.current = null;
  }

  function openInfo(entry: Entry) {
    const map = mapRef.current;
    if (!map || !infoRef.current) return;
    const { sel, order: ord, phase: ph } = live.current;
    infoRef.current.setContent(popupEl(entry.group, ord, sel, ph, closeInfo, (id) => live.current.select(id)));
    infoRef.current.open(map, entry.marker);
    openKeyRef.current = entry.group.key;
  }

  function fit(onlySelected: boolean) {
    const naver = window.naver;
    const map = mapRef.current;
    if (!naver?.maps || !map) return false;
    const sel = onlySelected ? selectedManagerId : null;
    const pts: Array<[number, number]> = [];
    for (const g of groups) if (sel == null || g.items.some((x) => x.manager_id === sel)) pts.push([g.latitude, g.longitude]);
    for (const r of effectiveRoutes) {
      if (sel != null && r.manager_id !== sel) continue;
      for (const p of [...(r.completed_path ?? []), ...(r.remaining_path ?? [])]) if (okPt(p)) pts.push([p.lat, p.lng]);
    }
    if (pts.length === 0) return false;
    if (pts.length === 1) {
      map.setCenter(new naver.maps.LatLng(pts[0][0], pts[0][1]));
      map.setZoom(15);
      return true;
    }
    const p0 = new naver.maps.LatLng(pts[0][0], pts[0][1]);
    const bounds = new naver.maps.LatLngBounds(p0, p0);
    for (const [la, ln] of pts) bounds.extend(new naver.maps.LatLng(la, ln));
    map.fitBounds(bounds, FIT_MARGIN);
    return true;
  }

  // 1) 초기화
  useEffect(() => {
    let cancelled = false;
    loadNaverMaps()
      .then(() => {
        if (cancelled || !containerRef.current || mapRef.current) return;
        const naver = window.naver;
        const map = new naver.maps.Map(containerRef.current, {
          center: new naver.maps.LatLng(DEFAULT_CENTER.lat, DEFAULT_CENTER.lng),
          zoom: 11,
          zoomControl: true,
          zoomControlOptions: { position: naver.maps.Position.TOP_RIGHT },
          mapDataControl: false,
          scaleControl: true,
        });
        infoRef.current = new naver.maps.InfoWindow({
          content: "", backgroundColor: "transparent", borderWidth: 0, disableAnchor: true,
          pixelOffset: new naver.maps.Point(0, -18),
        });
        naver.maps.Event.addListener(map, "click", () => {
          if (Date.now() - overlayClickAt.current < 300) return;
          closeInfo();
        });
        mapRef.current = map;
        setReady(true);
      })
      .catch((e) => setMapError(e instanceof Error ? e.message : String(e)));
    return () => { cancelled = true; };
  }, []);

  // 1-1) 크기 변화(사이드바·목록 접기) 시 지도 크기 재계산
  //  - 바깥 상자(boxRef)만 감시: 지도가 안쪽 상자 크기를 바꿔도 다시 감지되지 않음
  //  - 크기가 실제로 달라졌을 때만, 한 프레임에 한 번만 setSize
  useEffect(() => {
    const box = boxRef.current;
    if (!ready || !box || typeof ResizeObserver === "undefined") return;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const naver = window.naver;
        const map = mapRef.current;
        if (!map || !naver?.maps) return;
        const w = box.clientWidth;
        const h = box.clientHeight;
        if (w < 10 || h < 10) return;
        const cur = map.getSize?.();
        if (cur && Math.round(cur.width) === w && Math.round(cur.height) === h) return;
        map.setSize(new naver.maps.Size(w, h));
      });
    });
    ro.observe(box);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [ready]);

  // 2) 마커 생성 — 배송 데이터 변경 시
  useEffect(() => {
    const naver = window.naver;
    const map = mapRef.current;
    if (!ready || !naver?.maps || !map) return;
    entriesRef.current.forEach((e) => e.marker.setMap(null));
    const { sel, order: ord, phase: ph } = live.current;
    entriesRef.current = groups.map((group) => {
      const st = markerStyle(naver, group, ord, sel, ph);
      const marker = new naver.maps.Marker({
        map, position: new naver.maps.LatLng(group.latitude, group.longitude),
        icon: st.icon, zIndex: st.zIndex,
        title: group.items[0]?.address_name || String(group.items[0]?.address_id ?? ""),
      });
      const entry: Entry = { marker, group };
      naver.maps.Event.addListener(marker, "click", () => {
        overlayClickAt.current = Date.now();
        openInfo(entry);
      });
      return entry;
    });
    const key = openKeyRef.current;
    if (key) {
      const e = entriesRef.current.find((x) => x.group.key === key);
      if (e) openInfo(e);
      else closeInfo();
    }
    setBuilt((v) => v + 1);
  }, [ready, groups]);

  // 3) 마커 모양 — 선택·번호·상태 변경 시 (재생성 없이 아이콘만)
  useEffect(() => {
    const naver = window.naver;
    if (!ready || !naver?.maps) return;
    for (const e of entriesRef.current) {
      const st = markerStyle(naver, e.group, order, selectedManagerId, phase);
      e.marker.setIcon(st.icon);
      e.marker.setZIndex(st.zIndex);
    }
    const key = openKeyRef.current;
    if (key) {
      const e = entriesRef.current.find((x) => x.group.key === key);
      if (e) openInfo(e);
    }
  }, [ready, built, order, selectedManagerId, phase]);

  // 4) 경로선
  useEffect(() => {
    const naver = window.naver;
    const map = mapRef.current;
    if (!ready || !naver?.maps || !map) return;
    linesRef.current.forEach((l) => l.setMap(null));
    linesRef.current = [];
    const sel = selectedManagerId;
    for (const r of effectiveRoutes) {
      const focus = sel != null && r.manager_id === sel;
      const dim = sel != null && !focus;
      const opacity = focus ? 1 : dim ? 0.18 : 0.85;
      const segments: Array<[Array<Pt> | undefined, boolean]> = [[r.completed_path, false], [r.remaining_path, true]];
      for (const [path, dashed] of segments) {
        const pts = (path ?? []).filter(okPt);
        if (pts.length < 2) continue;
        const line = new naver.maps.Polyline({
          map,
          path: pts.map((p) => new naver.maps.LatLng(p.lat, p.lng)),
          strokeColor: dim ? DIM_LINE : safeColor(r.manager_color),
          strokeOpacity: opacity,
          strokeWeight: focus ? 6 : dim ? 3 : 4,
          strokeLineCap: "round",
          strokeLineJoin: "round",
          zIndex: focus ? 50 : dim ? 5 : 20,
          clickable: true,
          ...(dashed ? { strokeStyle: "shortdash" } : {}),
        });
        naver.maps.Event.addListener(line, "click", () => {
          overlayClickAt.current = Date.now();
          live.current.select(r.manager_id);
        });
        linesRef.current.push(line);
      }
    }
  }, [ready, effectiveRoutes, selectedManagerId]);

  // 5) 출발지
  useEffect(() => {
    const naver = window.naver;
    const map = mapRef.current;
    if (!ready || !naver?.maps || !map) return;
    const r = effectiveRoutes.find((x) => Number.isFinite(x.origin_latitude) && Number.isFinite(x.origin_longitude));
    if (!r) {
      originRef.current?.setMap(null);
      originRef.current = null;
      return;
    }
    const pos = new naver.maps.LatLng(r.origin_latitude as number, r.origin_longitude as number);
    if (originRef.current) {
      originRef.current.setPosition(pos);
      return;
    }
    originRef.current = new naver.maps.Marker({
      map, position: pos,
      icon: { content: `<div class="mk-origin">출발</div>`, anchor: new naver.maps.Point(22, 31) },
      title: r.origin_name ?? "출발지", zIndex: 400,
    });
  }, [ready, effectiveRoutes]);

  // 6) 자동 맞춤 — 날짜·선택 변경 시에만
  useEffect(() => {
    if (!ready || loading || fitKeyRef.current === autoFitKey) return;
    if (fit(true)) fitKeyRef.current = autoFitKey;
  }, [ready, loading, autoFitKey, groups, effectiveRoutes]);

  const onShowAll = () => {
    if (selectedManagerId != null) select(null);
    else fit(false);
  };

  const sr = selectedManagerId == null ? null : effectiveRoutes.find((r) => r.manager_id === selectedManagerId) ?? null;
  const selRow = rows.find((r) => r.id === selectedManagerId) ?? null;
  const missingNo = useMemo(() => {
    if (selectedManagerId == null || !selRow?.hasOrder) return 0;
    return stops.filter((s) => s.manager_id === selectedManagerId && stopNo(s, order) == null).length;
  }, [stops, order, selectedManagerId, selRow]);
  const srcLabel: Record<string, string> = { cache: "캐시", naver: "새 계산", pending: "경로 계산 전", unavailable: "경로선 없음" };

  return (
    <Panel
      title="배송 지도"
      right={
        <>
          {routesLoading && <span className="muted small">경로 불러오는 중…</span>}
          <Button size="sm" variant="ghost" onClick={() => setListOpen((v) => !v)}>
            {listOpen ? "목록 접기" : "노선 목록"}
          </Button>
          {selectedManagerId != null && (
            <>
              <Button size="sm" onClick={() => step(-1)} aria-label="이전 노선">‹</Button>
              <Button size="sm" onClick={() => step(1)} aria-label="다음 노선">›</Button>
              <Button size="sm" onClick={() => fit(true)}>노선 맞춤</Button>
            </>
          )}
          <Button size="sm" onClick={onShowAll}>전체 보기</Button>
        </>
      }
    >
      {mapError && <div className="stack"><ErrorBox message={mapError} /></div>}

      <div className={`map-layout${listOpen && rows.length > 0 ? "" : " no-list"}`}>
        {listOpen && rows.length > 0 && (
          <aside className="rl" aria-label="노선 목록">
            <div className="rl-tools">
              <input className="input input-sm grow" value={q} onChange={(e) => setQ(e.target.value)} placeholder="매니저 검색" />
              <select className="input input-sm" value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="정렬">
                <option value="name">이름순</option>
                <option value="todo">배송전 많은 순</option>
                <option value="stops">배송지 많은 순</option>
              </select>
            </div>
            <div className="rl-body" ref={listRef} tabIndex={0} onKeyDown={onListKey}>
              <button
                type="button" data-id="all"
                className={`rl-row${selectedManagerId == null ? " active" : ""}`}
                onClick={() => select(null)}
              >
                <div className="rl-line">
                  <span className="rl-name">전체 노선 {num(rows.length)}개</span>
                  <span className="rl-count">{phase === "preview" ? num(totals.stops) : `${num(totals.done)}/${num(totals.stops)}`}</span>
                </div>
              </button>
              {listRows.map((r) => {
                const active = r.id === selectedManagerId;
                const pct = r.stops > 0 ? Math.round((r.done / r.stops) * 100) : 0;
                return (
                  <button
                    key={r.id} type="button" data-id={r.id}
                    className={`rl-row${active ? " active" : ""}${selectedManagerId != null && !active ? " faded" : ""}`}
                    style={{ "--c": r.color } as CSSProperties}
                    onClick={() => select(active ? null : r.id)}
                    title={active ? "다시 누르면 전체 보기" : `${r.name} 노선만 보기`}
                  >
                    <div className="rl-line">
                      <span className="dot" style={{ background: r.color }} />
                      <span className="rl-name">{r.name}</span>
                      <span className="rl-count">{phase === "preview" ? `${num(r.stops)}곳` : `${num(r.done)}/${num(r.stops)}`}</span>
                    </div>
                    {phase !== "preview" && <div className="rl-bar"><i style={{ width: `${pct}%` }} /></div>}
                    <div className="rl-meta">
                      {num(r.meals)}식
                      {r.hasLine && r.km > 0 ? ` · ${r.km.toFixed(1)}km` : ""}
                      {r.hasLine && r.min > 0 ? ` · ${fmtMin(r.min)}` : ""}
                      {!r.hasLine ? " · 경로선 없음" : ""}
                    </div>
                  </button>
                );
              })}
              {listRows.length === 0 && <div className="rl-foot">검색 결과가 없습니다.</div>}
            </div>
            <div className="rl-foot">
              ↑↓ 노선 이동 · Esc 전체{totals.unassigned > 0 ? ` · 미배정 ${num(totals.unassigned)}곳` : ""}
            </div>
          </aside>
        )}
        <div ref={boxRef} className="map-box">
          <div ref={containerRef} className="map-canvas" />
        </div>        
      </div>

      <div className="map-foot">
        {sr || selRow ? (
          <>
            <Chip>
              <span className="dot" style={{ background: selRow?.color ?? safeColor(sr?.manager_color) }} />
              {selRow?.name ?? sr?.manager_name ?? selectedManagerId}
            </Chip>
            {sr && sr.distance_m > 0 && <Chip>총 {(sr.distance_m / 1000).toFixed(1)}km</Chip>}
            {sr && sr.duration_ms > 0 && <Chip>예상 {fmtMin(sr.duration_ms / 60000)}</Chip>}
            {phase !== "preview" && selRow && <Chip tone="ok">완료 {num(selRow.done)}</Chip>}
            {phase !== "preview" && selRow && (
              <Chip tone={phase === "live" ? "caution" : "danger"}>
                {phase === "live" ? "배송전" : "미완료"} {num(selRow.stops - selRow.done)}
              </Chip>
            )}
            {sr && sr.toll_fare > 0 && <Chip>통행료 {won(sr.toll_fare)}</Chip>}
            {sr && (sr.fuel_price_naver ?? 0) > 0 && <Chip>유류비(NAVER) {won(sr.fuel_price_naver)}</Chip>}
            {sr && (sr.fuel_price_opinet ?? 0) > 0 && <Chip>유류비(오피넷) {won(sr.fuel_price_opinet as number)}</Chip>}
            {missingNo > 0 && <Chip tone="caution" title="노선 순서 정보와 배송건 ID가 맞지 않는 배송지">번호 없음 {num(missingNo)}곳</Chip>}
            {selRow && !selRow.hasOrder && <Chip tone="caution">순서 정보 없음</Chip>}
            {sr?.origin_name && <span className="muted small">출발지 {sr.origin_name}</span>}
            {sr && <span className="muted small">· {srcLabel[sr.source] ?? sr.source}</span>}
          </>
        ) : (
          <div className="map-legend">
            {phase === "preview" ? (
              <span className="lg"><i className="lg-mk st-plan" />예상 배송지</span>
            ) : (
              <>
                <span className="lg"><i className="lg-mk st-done" />완료</span>
                {phase === "live" && <span className="lg"><i className="lg-mk st-todo" />배송전</span>}
                <span className="lg"><i className="lg-mk st-miss" />미완료</span>
              </>
            )}
            <span className="muted small">숫자 = 도착 순서 · 같은 위치는 5-6 · 실선 완료 / 점선 배송전 경로</span>
          </div>
        )}
      </div>
    </Panel>
  );
}
