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
  
  /** JS 객체는 "2","4","23" 같은 숫자 키를 오름차순으로 재정렬하므로 라인업 순서를 직접 고정한다. */
  const LINEUP_ORDER = ["4", "23", "29", "2"];
  export function orderedLineups<T>(obj: Record<string, T>): Array<[string, T]> {
    const rank = (k: string) => {
      const i = LINEUP_ORDER.indexOf(k);
      return i < 0 ? 99 : i;
    };
    return Object.entries(obj).sort(([a], [b]) => rank(a) - rank(b));
  }
  