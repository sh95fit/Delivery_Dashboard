import { ApiError, del, http, post, put } from "./client";
import type { IncomeType } from "./workers";

export interface WorkContract {
  amount: number; work_start: string | null; work_end: string | null;
  break_min: number; break_paid: boolean; has_ot_rule: boolean; vat_applied: boolean; work_days: number;
}
export interface WorkLog {
  id: number; work_date: string; punch_in: string | null; clock_in: string; clock_out: string;
  break_min: number | null; manager_id: number | null; memo: string | null; source: string | null;
  paid_min: number | null; ot_min: number | null; ot_pay: number | null; sheet_break: number | null;
  no_contract: boolean;
}
export type OffReason = "annual" | "sick" | "personal" | "factory" | "holiday" | "other";
export const OFF_REASONS: Array<[OffReason, string]> = [
  ["annual", "연차·휴가"], ["sick", "병가"], ["personal", "개인 사정"],
  ["factory", "공장 휴무"], ["holiday", "공휴일"], ["other", "기타"],
];
export const OFF_LABEL = Object.fromEntries(OFF_REASONS) as Record<OffReason, string>;
export interface WorkOff { id: number; work_date: string; reason: OffReason; memo: string | null }
export type WorkOffInput = { work_date: string; reason: OffReason; memo: string | null };
export interface WorkDayItem {
  worker_id: number; name: string; income_type: IncomeType; active: boolean;
  contract: WorkContract | null; fixed_manager_id: number | null; fixed_manager_name: string | null;
  log: WorkLog | null; off: WorkOff | null; workday: boolean;
}
export interface WorkDayView { date: string; closed: boolean; future: boolean; items: WorkDayItem[] }
export interface PaySet { supply: number; vat: number; total: number }
export interface WorkMonthPerson {
  worker_id: number; name: string; income_type: IncomeType; active: boolean;
  sheet: "labor" | "business" | null; contract: WorkContract | null; contracts: ContractSpan[]; accounts: AccountSpan[];
  days: Record<string, WorkLog>; offs: Record<string, WorkOff>; missing_days: number[];
  summary: { days: number; nocontract: number; paid_min: number; ot_min: number; base: number; ot_allow: number; weekend_days: number; weekend_min: number };
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
  ok: boolean; saved: number; unchanged: number; deleted: number; off_saved: number; off_deleted: number; warns: Record<string, string[]>;
}
export const saveWorkPerson = (wid: number, items: WorkLogDateInput[], delete_ids: number[],
  offs: WorkOffInput[] = [], off_delete_ids: number[] = []) =>
  put<SavePersonResult>(`/api/worklogs/person/${wid}`, { items, delete_ids, offs, off_delete_ids });

export interface BulkOffResult { ok: boolean; saved: number; released: number; unchanged: number; skipped: string[] }

/** 하루 × 여러 사람 휴무 지정(reason) / 해제(reason=null) */
export const saveWorkOffs = (d: string, worker_ids: number[], reason: OffReason | null, memo: string | null) =>
  put<BulkOffResult>(`/api/worklogs/offs/${d}`, { worker_ids, reason, memo });    

/* ---------- S2-P4b-2 월 마감 ---------- */
export interface CloseIssue {
  level: "error" | "warn" | "info"; worker_id: number | null; name: string | null; day: number | null; msg: string;
}
export interface CloseTotals { people: number; days: number; paid_min: number; sheet_total: number }
export interface ClosingRow {
  id: number; closed_at: string | null; closed_by: string | null; memo: string | null;
  reopened_at: string | null; reopened_by: string | null; reopen_reason: string | null; summary: CloseTotals | null;
}
export interface CloseCheck {
  month: string; closed: boolean; ended: boolean; can_close: boolean;
  issues: CloseIssue[]; totals: CloseTotals; history: ClosingRow[];
}
export const getCloseCheck = (month: string) => http<CloseCheck>(`/api/worklogs/close/check?month=${month}`);
export const closeMonth = (month: string, memo: string | null) =>
  post<{ ok: boolean; totals: CloseTotals }>("/api/worklogs/close", { month, memo });
export const reopenMonth = (month: string, reason: string) =>
  post<{ ok: boolean }>("/api/worklogs/reopen", { month, reason });

/** 근무 요일 판정 (서버 is_workday와 같은 규칙): 월=1 … 일=64 */
export const dayBit = (iso: string) => 1 << ((new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7);
export const isWorkday = (c: WorkContract | null, iso: string) => !!c && (c.work_days & dayBit(iso)) !== 0;

/** 시작일 순 이력에서 d 날짜에 적용되는 항목 */
export function spanOn<T extends { from: string }>(spans: T[], d: string): T | null {
  let hit: T | null = null;
  for (const s of spans) if (s.from <= d) hit = s;
  return hit;
}

/* ---------- S2-P4a-2b 근무표 엑셀 다운로드 ---------- */
export type SheetKind = "labor" | "business";
export type ExportKind = "all" | SheetKind;
export interface ExportQuery {
  month: string; sheet: ExportKind; start?: string; end?: string; ids?: number[];
}
export interface ExportPerson {
  worker_id: number; name: string; active: boolean; rate: number; note: string | null;
  work_days: number; paid_min: number; base: number; sheet_total: number;
  incentive: number; weekend: number; vat: boolean;
}
export interface ExportIssue { level: "error" | "warn" | "info"; sheet: SheetKind | null; name: string | null; msg: string }
export interface ExportPlan {
  month: string; start: string; end: string; closed: boolean;
  sheets: Record<SheetKind, ExportPerson[]>; issues: ExportIssue[]; ok: Record<SheetKind, boolean>;
}

function exportQs(q: ExportQuery, withSheet: boolean): string {
  const p = new URLSearchParams({ month: q.month });
  if (withSheet) p.set("sheet", q.sheet);
  if (q.start) p.set("start", q.start);
  if (q.end) p.set("end", q.end);
  for (const id of q.ids ?? []) p.append("ids", String(id));   // 서버: ids=1&ids=2
  return p.toString();
}

export const getExportPlan = (q: ExportQuery) => http<ExportPlan>(`/api/worklogs/export/plan?${exportQs(q, false)}`);

/** 파일을 받아 브라우저 저장 → 저장된 파일명 반환 */
export async function downloadTimesheet(q: ExportQuery): Promise<string> {
  let res: Response;
  try {
    res = await fetch(`/api/worklogs/export?${exportQs(q, true)}`, { credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network_error", "네트워크 연결에 실패했습니다. 잠시 후 다시 시도하세요.");
  }
  if (res.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "unauthorized", "로그인이 필요합니다.");
  }
  if (res.status === 403) throw new ApiError(403, "forbidden", "근무표 다운로드는 관리자만 할 수 있습니다.");
  if (!res.ok) {
    let msg = res.statusText || "근무표 생성 실패";
    try {
      const j = JSON.parse(await res.text());
      if (typeof j?.detail === "string") msg = j.detail;
    } catch { /* JSON 아님 */ }
    throw new ApiError(res.status, "server_error", msg);
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const m = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : "근무시간표.xlsx";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return name;
}
