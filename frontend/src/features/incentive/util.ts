import type { ChipTone } from "@/components/ui/Chip";
import type { Band, IncDayRow, IncStatus } from "@/api/incentive";
import { num } from "@/lib/format";

const WD = "일월화수목금토";
export const wd = (d: string) => WD[new Date(`${d}T00:00:00Z`).getUTCDay()];
export function shift(d: string, n: number) {
  const t = new Date(`${d}T00:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}
export const amt = (n: number | null | undefined) => (n == null ? "-" : num(n));
export const wonOr = (n: number | null | undefined) => (n == null ? "-" : `${num(n)}원`);

export const STATUS: Record<IncStatus, [string, ChipTone]> = {
  ok: ["확정", "ok"],
  need_accounts: ["고객사 수 입력 필요", "caution"],
  held: ["미지급", "danger"],
  no_rate: ["단가표 없음", "warn"],
};

/** "20,000" / "20000원" → 20000. 1원 ~ 100만 원 정수만, 그 외 null */
export function parseAmt(s: string): number | null {
  const t = s.replace(/[,\s원]/g, "");
  if (!/^\d{1,7}$/.test(t)) return null;
  const n = Number(t);
  return n >= 1 && n <= 1_000_000 ? n : null;
}

export const bandText = (b: Band) =>
  b.end == null ? `${num(b.start)} 초과 (끝 없음)` : `${num(b.start)} 초과 ~ ${num(b.end)} 이하`;

/** 제외·조정 칸: "−12 +3" */
export function adjText(r: Pick<IncDayRow, "excluded_qty" | "delta">) {
  const p: string[] = [];
  if (r.excluded_qty) p.push(`−${num(r.excluded_qty)}`);
  if (r.delta) p.push(`${r.delta > 0 ? "+" : "−"}${num(Math.abs(r.delta))}`);
  return p.length ? p.join(" ") : "-";
}
