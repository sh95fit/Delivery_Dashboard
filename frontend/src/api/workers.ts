import { del, http, post, put } from "./client";
import { won } from "@/lib/format";
import type { PayType } from "./masters";

export type IncomeType = "regular" | "employee" | "business" | "freelancer";
export const INCOME_LABEL: Record<IncomeType, string> = {
  regular: "정규직", employee: "근로소득", business: "사업자", freelancer: "프리랜서",
};
/** 정규직 = 월급(+인센티브), 그 외 = 시급제 */
export const INCOME_PAY: Record<IncomeType, PayType> = {
  regular: "monthly", employee: "hourly", business: "hourly", freelancer: "hourly",
};

export interface WorkerRate {
  id: number; effective_from: string; pay_type: PayType; amount: number; vat_applied: boolean;
  work_start: string | null; work_end: string | null; break_min: number; break_paid: boolean;
  ot_unit_min: number; ot_unit_amount: number; paid_min: number; daily_base: number | null;
  memo?: string | null; created_by?: string | null;
}
export interface WorkerAccount {
  id: number; manager_id: number | null; start_date: string;
  manager_name: string | null; manager_color: string | null; created_by?: string | null;
}
export interface WorkerRow {
  id: number; name: string; income_type: IncomeType; active: boolean; memo: string | null;
  legacy_manager_id: number | null; updated_at: string | null; updated_by: string | null;
  rate: WorkerRate | null; account: WorkerAccount | null;
}
export interface WorkerDetail { rates: WorkerRate[]; accounts: WorkerAccount[] }

export type WorkerInput = { name: string; income_type: IncomeType; active: boolean; memo: string | null };
export type WorkerRateInput = {
  effective_from: string; pay_type: PayType; amount: number; vat_applied: boolean; memo: string | null;
  work_start?: string; work_end?: string; break_min?: number; break_paid?: boolean;
  ot_unit_min?: number; ot_unit_amount?: number;
};
type Ok = { ok: boolean; id?: number };

export const listWorkers = () => http<{ items: WorkerRow[] }>("/api/workers");
export const getWorker = (id: number) => http<WorkerDetail>(`/api/workers/${id}`);
export const createWorker = (body: WorkerInput) => post<Ok>("/api/workers", body);
export const updateWorker = (id: number, body: WorkerInput) => put<Ok>(`/api/workers/${id}`, body);
export const addWorkerRate = (id: number, body: WorkerRateInput) => post<Ok>(`/api/workers/${id}/rates`, body);
export const deleteWorkerRate = (rid: number) => del<Ok>(`/api/workers/rates/${rid}`);
export const assignWorkerAccount = (id: number, body: { manager_id: number | null; start_date: string }) =>
  post<Ok>(`/api/workers/${id}/accounts`, body);
export const deleteWorkerAccount = (aid: number) => del<Ok>(`/api/workers/accounts/${aid}`);

export const rateText = (r: WorkerRate) =>
  r.pay_type === "none" ? "인건비 없음" : `${r.pay_type === "monthly" ? "월급" : "시급"} ${won(r.amount)}`;
export const workText = (r: WorkerRate) => {
  if (!r.work_start || !r.work_end) return "-";
  const brk = r.break_min ? ` · 휴게 ${r.break_min}분 ${r.break_paid ? "유급" : "무급"}` : "";
  return `${r.work_start}–${r.work_end}${brk}`;
};
export const otText = (r: WorkerRate) =>
  r.ot_unit_min > 0 && r.ot_unit_amount > 0 ? `${r.ot_unit_min}분당 ${won(r.ot_unit_amount)}` : "없음";
export const needsName = (w: WorkerRow) => w.name.startsWith("계정#");
