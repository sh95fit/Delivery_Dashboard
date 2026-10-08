import { toMin } from "@/api/worklogs";
import type { WorkContract, WorkLog } from "@/api/worklogs";

export type LogForm = { punch: string; out: string; brk: string; mid: string; memo: string };
export const EMPTY_FORM: LogForm = { punch: "", out: "", brk: "", mid: "", memo: "" };

export function logToForm(l: WorkLog | null): LogForm {
  if (!l) return EMPTY_FORM;
  return {
    punch: l.punch_in ?? "", out: l.clock_out ?? "", brk: l.break_min == null ? "" : String(l.break_min),
    mid: l.manager_id == null ? "" : String(l.manager_id), memo: l.memo ?? "",
  };
}
export const sameForm = (a: LogForm, b: LogForm) =>
  a.punch === b.punch && a.out === b.out && a.brk === b.brk && a.mid === b.mid && a.memo.trim() === b.memo.trim();
export const defaultBreak = (c: WorkContract | null) => (c ? (c.break_paid ? 0 : c.break_min) : 0);

/** 화면 미리보기. 저장 시 서버가 같은 규칙으로 다시 계산·검증 */
export function preview(c: WorkContract | null, f: LogForm): { cin: number | null; paid: number | null; err: string } {
  const ws = toMin(c?.work_start);
  const out = toMin(f.out);
  if (!c || ws == null || out == null) return { cin: null, paid: null, err: "" };
  const cin = Math.max(toMin(f.punch) ?? ws, ws);
  const brk = f.brk !== "" ? Number(f.brk) : defaultBreak(c);
  if (out <= cin) return { cin, paid: null, err: "퇴근이 출근보다 빠름" };
  if (brk >= out - cin) return { cin, paid: null, err: "휴게가 근무보다 김" };
  return { cin, paid: out - cin - brk, err: "" };
}
