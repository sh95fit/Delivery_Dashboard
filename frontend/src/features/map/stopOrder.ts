import type { StatusState, StopPoint } from "@/api/types";

/* [S3-P2k] 배송지 번호 — 지도 마커·노선 상세·지연 목록이 같은 번호를 쓰도록 한 곳에서 계산
   진행 중: 완료한 곳 = 완료 시각순 → 남은 곳 = 앱 배송 순서(delivery.ordering)대로 이어서
   종료 후: 완료 시각순만 / 배송 전: 앱 배송 순서(없으면 희망 시각) */
export type OrderPhase = "preview" | "live" | "result";
type Pt = { lat: number; lng: number };

export const phaseOf = (s?: StatusState): OrderPhase => (s === "LIVE" ? "live" : s === "RESULT" ? "result" : "preview");

const hasXY = (s: StopPoint) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude);
const xy = (s: StopPoint): Pt => ({ lat: s.latitude as number, lng: s.longitude as number });
const dist2 = (a: Pt, s: StopPoint) =>
  (a.lat - (s.latitude as number)) ** 2 + ((a.lng - (s.longitude as number)) * 0.8) ** 2;
const doneAt = (s: StopPoint) => new Date(s.delivered_at as string).getTime();
export const byId = (a: StopPoint, b: StopPoint) => String(a.delivery_id).localeCompare(String(b.delivery_id));

/** start에서 가장 가까운 곳을 차례로 고른다 */
function nearestChain(list: StopPoint[], start: Pt | null): { out: StopPoint[]; end: Pt | null } {
  const rest = list.slice().sort(byId);
  const out: StopPoint[] = [];
  let cur = start;
  while (rest.length) {
    let bi = 0;
    if (cur) {
      let bd = Infinity;
      rest.forEach((s, i) => {
        const d = hasXY(s) ? dist2(cur!, s) : Infinity;
        if (d < bd) { bd = d; bi = i; }
      });
    }
    const [s] = rest.splice(bi, 1);
    out.push(s);
    if (hasXY(s)) cur = xy(s);
  }
  return { out, end: cur };
}

/** 같은 키(순서 값 또는 희망시간)끼리 묶어 키 순서대로, 묶음 안은 직전 위치에서 가까운 곳부터 */
function chainBy<K extends string | number>(list: StopPoint[], key: (s: StopPoint) => K, start: Pt | null) {
  const groups = new Map<K, StopPoint[]>();
  for (const s of list) {
    const k = key(s);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(s);
  }
  const out: StopPoint[] = [];
  let cur = start;
  for (const k of [...groups.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))) {
    const r = nearestChain(groups.get(k)!, cur);
    out.push(...r.out);
    cur = r.end;
  }
  return { out, end: cur };
}

/** 키 = `${manager_id}:${delivery_id}` → 번호 */
export function buildStopOrder(stops: StopPoint[], phase: OrderPhase, origin: Pt | null) {
  const order = new Map<string, number>();
  const byMgr = new Map<number, StopPoint[]>();
  for (const s of stops) {
    if (s.manager_id == null) continue;
    if (!byMgr.has(s.manager_id)) byMgr.set(s.manager_id, []);
    byMgr.get(s.manager_id)!.push(s);
  }
  for (const [mid, list] of byMgr) {
    const done = phase === "preview" ? [] : list
      .filter((s) => s.delivered_at)
      .sort((a, b) => doneAt(a) - doneAt(b) || byId(a, b));
    const todo = phase === "result" ? [] : list.filter((s) => !s.cancelled && (phase === "preview" || !s.delivered_at));
    const last = [...done].reverse().find(hasXY);
    const a = chainBy(todo.filter((s) => s.seq != null), (s) => s.seq as number, last ? xy(last) : origin);
    const b = chainBy(todo.filter((s) => s.seq == null), (s) => s.delivery_time || "99:99", a.end);
    const ordered = [...done, ...a.out, ...b.out];
    ordered.forEach((s, i) => order.set(`${mid}:${s.delivery_id}`, i + 1));
  }
  return order;
}

export function stopNo(s: StopPoint, order: Map<string, number>) {
  return s.manager_id == null ? undefined : order.get(`${s.manager_id}:${s.delivery_id}`);
}
