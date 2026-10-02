export function num(n?: number | null): string {
    return (n ?? 0).toLocaleString("ko-KR");
  }
  
export function won(n?: number | null): string {
  return `${num(n)}원`;
}

export function kstDateTime(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** JS 객체는 숫자 키를 오름차순으로 재정렬하므로 라인업 순서를 직접 고정한다. order는 API의 lineup_meta 순서 */
const LINEUP_ORDER = ["4", "23", "29", "2", "31", "30"];
export function orderedLineups<T>(obj: Record<string, T>, order?: string[]): Array<[string, T]> {
  const ord = order && order.length ? order : LINEUP_ORDER;
  const rank = (k: string) => {
    const i = ord.indexOf(k);
    return i < 0 ? 99 : i;
  };
  return Object.entries(obj).sort(([a], [b]) => rank(a) - rank(b));
}

/** KST 기준 오늘 YYYY-MM-DD */
export function todayKst(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
}

/** "2026-10" → ["2026-10-01", "2026-10-31"] */
export function monthRange(ym: string): [string, string] {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return [`${ym}-01`, `${ym}-${String(last).padStart(2, "0")}`];
}
  
/** 분 → "5시간 30분" */
export function hm(min: number): string {
  const m = Math.max(0, Math.round(min));
  const h = Math.floor(m / 60);
  const r = m % 60;
  return h ? (r ? `${h}시간 ${r}분` : `${h}시간`) : `${r}분`;
}
