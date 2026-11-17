import { toMin } from "@/api/worklogs";
import type { WorkContract, WorkLog, WorkLogInput, WorkOff } from "@/api/worklogs";
import { workDaysText } from "@/api/workers";

/** 화면 입력값. 출근·휴게는 그날 계약 기본값을 채워 보여주고,
 *  저장 시 기본값과 같으면 NULL(= 계약 따름)로 보냄 → 계약 수정 시 그날도 따라감
 *  off = 휴무 사유 코드 ("" = 근무일) */
export type LogForm = { punch: string; out: string; brk: string; mid: string; memo: string; off: string; early: boolean; ride: boolean };
export const EMPTY_FORM: LogForm = { punch: "", out: "", brk: "", mid: "", memo: "", off: "", early: false, ride: false };

/** 휴게 칸 기본값 = 인력 계약의 휴게 시간 (유급·무급 모두 실제 휴게 분) */
export const defaultBreak = (c: WorkContract | null) => (c ? c.break_min : 0);
/** 유급시간에서 빼는 분: 계약이 유급 휴게면 0 (서버 sheet_break와 같은 규칙) */
export const deductOf = (c: WorkContract | null, brk: number) => (c?.break_paid ? 0 : brk);
export const defaultIn = (c: WorkContract | null) => c?.work_start ?? "";
/** 조기 출근 인정 체크를 보여줄지: 지문 출근이 지정 출근보다 이를 때만 */
export const earlyAble = (c: WorkContract | null, punch: string) => {
  const p = toMin(punch), ws = toMin(c?.work_start);
  return p != null && ws != null && p < ws;
};

export const isDefaultIn = (c: WorkContract | null, v: string) =>
  v === "" || (c != null && toMin(v) === toMin(c.work_start));
export const isDefaultBreak = (c: WorkContract | null, v: string) =>
  v === "" || (c != null && Number(v) === defaultBreak(c));

export function logToForm(l: WorkLog | null, c: WorkContract | null, o: WorkOff | null = null): LogForm {
  return {
    punch: l?.punch_in ?? defaultIn(c),
    out: l?.clock_out ?? "",
    brk: l?.break_min != null ? String(l.break_min) : c ? String(defaultBreak(c)) : "",
    mid: l?.manager_id == null ? "" : String(l.manager_id),
    memo: l?.memo ?? o?.memo ?? "",
    off: o?.reason ?? "",
    early: !!l?.early_ok,
    ride: !!l?.ride_along,    
  };
}

export const sameForm = (a: LogForm, b: LogForm) =>
  a.punch === b.punch && a.out === b.out && a.brk === b.brk && a.mid === b.mid &&
  a.memo.trim() === b.memo.trim() && a.off === b.off && a.early === b.early && a.ride === b.ride;

/** 저장 요청 값: 기본값과 같은 칸은 NULL */
export function toInput(c: WorkContract | null, f: LogForm): Omit<WorkLogInput, "worker_id"> {
  return {
    punch_in: isDefaultIn(c, f.punch) ? null : f.punch,
    clock_out: f.out,
    break_min: isDefaultBreak(c, f.brk) ? null : Number(f.brk),
    manager_id: f.mid === "" ? null : Number(f.mid),
    memo: f.memo.trim() || null,
    early_ok: f.early && earlyAble(c, f.punch),
    ride_along: f.ride && f.mid !== "",   // [S2-P4e] 동승 (계정 없으면 화면에서 저장 차단)    
  };
}

/** '07:00–12:30 · 휴게 30분(유급)' (+ 월~금이 아니면 요일) */
export function contractText(c: WorkContract | null): string {
  if (!c) return "";
  const b = c.break_min > 0 ? ` · 휴게 ${c.break_min}분${c.break_paid ? "(유급)" : ""}` : "";
  const d = c.work_days !== 31 ? ` · ${workDaysText(c.work_days)}` : "";
  return `${c.work_start}–${c.work_end}${b}${d}`;
}

/** 화면 미리보기. 저장 시 서버가 같은 규칙으로 다시 계산·검증 */
export function preview(c: WorkContract | null, f: LogForm): { cin: number | null; paid: number | null; err: string } {
  const ws = toMin(c?.work_start);
  const out = toMin(f.out);
  if (!c || ws == null || out == null) return { cin: null, paid: null, err: "" };
  if (f.ride && f.mid === "") return { cin: null, paid: null, err: "동승 계정 선택" };   // [S2-P4e] 서버 검사와 같은 규칙
  const p = toMin(f.punch);
  const cin = f.early && p != null && p < ws ? p : Math.max(p ?? ws, ws);
  const badBrk = f.brk !== "" && (!/^\d{1,3}$/.test(f.brk) || Number(f.brk) > 600);
  if (badBrk) return { cin, paid: null, err: "휴게 0~600분" };
  const brk = f.brk !== "" ? Number(f.brk) : defaultBreak(c);
  if (out <= cin) return { cin, paid: null, err: "퇴근이 출근보다 빠름" };
  if (brk >= out - cin) return { cin, paid: null, err: "휴게가 근무보다 김" };
  return { cin, paid: out - cin - deductOf(c, brk), err: "" };
}
