import { toMin } from "@/api/worklogs";
import type { WorkContract, WorkLog, WorkLogInput } from "@/api/worklogs";

/** 화면 입력값. 출근·휴게는 그날 계약 기본값을 채워 보여주고,
 *  저장 시 기본값과 같으면 NULL(= 계약 따름)로 보냄 → 계약 수정 시 그날도 따라감 */
export type LogForm = { punch: string; out: string; brk: string; mid: string; memo: string };
export const EMPTY_FORM: LogForm = { punch: "", out: "", brk: "", mid: "", memo: "" };

/** 근무표 '휴게' 칸 기본값 = 유급시간에서 빼는 분 (무급 휴게만) */
export const defaultBreak = (c: WorkContract | null) => (c ? (c.break_paid ? 0 : c.break_min) : 0);
export const defaultIn = (c: WorkContract | null) => c?.work_start ?? "";

export const isDefaultIn = (c: WorkContract | null, v: string) =>
  v === "" || (c != null && toMin(v) === toMin(c.work_start));
export const isDefaultBreak = (c: WorkContract | null, v: string) =>
  v === "" || (c != null && Number(v) === defaultBreak(c));

export function logToForm(l: WorkLog | null, c: WorkContract | null): LogForm {
  return {
    punch: l?.punch_in ?? defaultIn(c),
    out: l?.clock_out ?? "",
    brk: l?.break_min != null ? String(l.break_min) : c ? String(defaultBreak(c)) : "",
    mid: l?.manager_id == null ? "" : String(l.manager_id),
    memo: l?.memo ?? "",
  };
}

export const sameForm = (a: LogForm, b: LogForm) =>
  a.punch === b.punch && a.out === b.out && a.brk === b.brk && a.mid === b.mid && a.memo.trim() === b.memo.trim();

/** 저장 요청 값: 기본값과 같은 칸은 NULL */
export function toInput(c: WorkContract | null, f: LogForm): Omit<WorkLogInput, "worker_id"> {
  return {
    punch_in: isDefaultIn(c, f.punch) ? null : f.punch,
    clock_out: f.out,
    break_min: isDefaultBreak(c, f.brk) ? null : Number(f.brk),
    manager_id: f.mid === "" ? null : Number(f.mid),
    memo: f.memo.trim() || null,
  };
}

/** '07:00–12:30 · 휴게 30분(유급)' */
export function contractText(c: WorkContract | null): string {
  if (!c) return "";
  const b = c.break_min > 0 ? ` · 휴게 ${c.break_min}분${c.break_paid ? "(유급)" : ""}` : "";
  return `${c.work_start}–${c.work_end}${b}`;
}

/** 화면 미리보기. 저장 시 서버가 같은 규칙으로 다시 계산·검증 */
export function preview(c: WorkContract | null, f: LogForm): { cin: number | null; paid: number | null; err: string } {
  const ws = toMin(c?.work_start);
  const out = toMin(f.out);
  if (!c || ws == null || out == null) return { cin: null, paid: null, err: "" };
  const cin = Math.max(toMin(f.punch) ?? ws, ws);
  const badBrk = f.brk !== "" && (!/^\d{1,3}$/.test(f.brk) || Number(f.brk) > 600);
  if (badBrk) return { cin, paid: null, err: "휴게 0~600분" };
  const brk = f.brk !== "" ? Number(f.brk) : defaultBreak(c);
  if (out <= cin) return { cin, paid: null, err: "퇴근이 출근보다 빠름" };
  if (brk >= out - cin) return { cin, paid: null, err: "휴게가 근무보다 김" };
  return { cin, paid: out - cin - brk, err: "" };
}
