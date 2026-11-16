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

/** +3 / −2 / 0 */
export const signed = (n: number) => (n > 0 ? `+${num(n)}` : n < 0 ? `−${num(-n)}` : "0");

/** [S2-P4c-3c] 서버 incentive_calc.band_pay 와 같은 규칙(금액만). 미리보기 전용 — 저장 후에는 서버 값 */
export function bandPay(q: number, bands: Band[]): number {
  const first = bands.find((b) => b.amount > 0);
  if (!first || q <= first.start) return 0;
  const b = bands.find((x) => x.start < q && (x.end == null || q <= x.end)) ?? bands[bands.length - 1];
  return (q - first.start) * b.amount;
}

export type IncPreview = { account: number | null; payable: number | null; total: number; status: IncStatus };

/** [S2-P4c-3c] 고객사 수를 바꿨을 때 그날 금액 미리보기 (서버 day_row 순서: 미지급 → 단가표 없음 → 입력 필요 → 확정).
 *  accounts=null(지움) → 입력 필요 */
export function previewDay(
  c: { product_incentive: number | null; held: boolean; extras: number },
  accounts: number | null, bands: Band[] | null | undefined,
): IncPreview {
  const account = bands && bands.length > 0 && accounts != null ? bandPay(accounts, bands) : null;
  if (c.held) return { account, payable: 0, total: c.extras, status: "held" };
  if (!bands || bands.length === 0 || c.product_incentive == null)
    return { account: null, payable: null, total: c.extras, status: "no_rate" };
  if (account == null) return { account: null, payable: null, total: c.extras, status: "need_accounts" };
  const payable = c.product_incentive + account;
  return { account, payable, total: payable + c.extras, status: "ok" };
}
