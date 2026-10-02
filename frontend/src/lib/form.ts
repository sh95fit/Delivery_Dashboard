export const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** "1,200,000원" → 1200000. 비었거나 정수가 아니면 NaN */
export function parseAmount(s: string): number {
  const v = s.replace(/[,\s원]/g, "");
  return v === "" || !/^\d+$/.test(v) ? NaN : Number(v);
}

/** 시작~종료 포함 일수 */
export function daysIncl(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000) + 1;
}

/** 2026-03-15 → 2027-03-14 (1년 기간 종료일) */
export function yearEnd(start: string): string {
  const d = new Date(`${start}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() + 1);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}
