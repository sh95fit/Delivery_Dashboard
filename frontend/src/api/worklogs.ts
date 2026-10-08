import { del, http, put } from "./client";
import type { IncomeType } from "./workers";

export interface WorkContract {
  amount: number; work_start: string | null; work_end: string | null;
  break_min: number; break_paid: boolean; has_ot_rule: boolean; vat_applied: boolean;
}
export interface WorkLog {
  id: number; work_date: string; punch_in: string | null; clock_in: string; clock_out: string;
  break_min: number | null; manager_id: number | null; memo: string | null; source: string | null;
  paid_min: number | null; ot_min: number | null; ot_pay: number | null; sheet_break: number | null;
  no_contract: boolean;
}
export interface WorkDayItem {
  worker_id: number; name: string; income_type: IncomeType; active: boolean;
  contract: WorkContract | null; fixed_manager_id: number | null; fixed_manager_name: string | null;
  log: WorkLog | null;
}
export interface WorkDayView { date: string; closed: boolean; future: boolean; items: WorkDayItem[] }
export interface PaySet { supply: number; vat: number; total: number }
export interface WorkMonthPerson {
  worker_id: number; name: string; income_type: IncomeType; active: boolean;
  sheet: "labor" | "business" | null; contract: WorkContract | null; contracts: ContractSpan[]; accounts: AccountSpan[];
  days: Record<string, WorkLog>;
  summary: { days: number; nocontract: number; paid_min: number; ot_min: number; base: number; ot_allow: number };
  pay: { sheet: PaySet; ot_allow: number | null; expected: PaySet | null };
}
export interface WorkMonthView { month: string; last_day: number; closed: boolean; people: WorkMonthPerson[] }
export type WorkLogInput = {
  worker_id: number; punch_in: string | null; clock_out: string; break_min: number | null;
  manager_id: number | null; memo: string | null;
};
export interface SaveDayResult { ok: boolean; saved: number; unchanged: number; warns: Record<string, string[]> }

export const getWorkDay = (d: string) => http<WorkDayView>(`/api/worklogs/day?d=${d}`);
export const getWorkMonth = (month: string) => http<WorkMonthView>(`/api/worklogs/month?month=${month}`);
export const saveWorkDay = (d: string, items: WorkLogInput[]) =>
  put<SaveDayResult>(`/api/worklogs/day/${d}`, { items });
export const deleteWorkLog = (id: number) => del<{ ok: boolean }>(`/api/worklogs/${id}`);

/** "07:05" → 425 */
export function toMin(s?: string | null): number | null {
  if (!s) return null;
  const m = /^(\d{1,2}):(\d{2})/.exec(s);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}
/** 425 → "7:05" (근무표 합계 표기) */
export const hmm = (m?: number | null) =>
  m == null ? "-" : `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;

/** 월 표 팝업용: 그 달에 적용되는 계약·고정 계정 이력 (시작일 순) */
export interface ContractSpan { from: string; contract: WorkContract | null }
export interface AccountSpan { from: string; manager_id: number | null; manager_name: string | null }
export type WorkLogDateInput = Omit<WorkLogInput, "worker_id"> & { work_date: string };
export interface SavePersonResult {
  ok: boolean; saved: number; unchanged: number; deleted: number; warns: Record<string, string[]>;
}
export const saveWorkPerson = (wid: number, items: WorkLogDateInput[], delete_ids: number[]) =>
  put<SavePersonResult>(`/api/worklogs/person/${wid}`, { items, delete_ids });

/** 시작일 순 이력에서 d 날짜에 적용되는 항목 */
export function spanOn<T extends { from: string }>(spans: T[], d: string): T | null {
  let hit: T | null = null;
  for (const s of spans) if (s.from <= d) hit = s;
  return hit;
}
