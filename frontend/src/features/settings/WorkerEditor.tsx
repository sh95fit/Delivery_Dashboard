import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import SaveNote, { nowHms } from "@/components/ui/SaveNote";
import type { SaveNoteState } from "@/components/ui/SaveNote";
import * as api from "@/api/workers";
import { DAY_BITS, DAY_REASON_LABEL, INCOME_LABEL, INCOME_PAY, VEHICLE_MODE_LABEL, needsName, otText, rateText, workText } from "@/api/workers";
import type { DayReason, IncomeType, VehicleMode, WorkerAccount, WorkerDetail, WorkerRate, WorkerRateInput, WorkerRow,
  WorkerVehicle, WorkerVehicleDay, WorkerVehicles } from "@/api/workers";
import { FUEL_LABEL, listVehicles } from "@/api/masters";
import type { ManagerRow, Vehicle } from "@/api/masters";
import { errText, parseAmount } from "@/lib/form";
import { hm, todayKst, won } from "@/lib/format";

type Tab = "basic" | "rate" | "account" | "vehicle";
type Mode = { kind: "add" } | { kind: "edit"; id: number } | null;
type RateForm = {
  amount: string; from: string; vat: boolean; ws: string; we: string;
  brk: string; brkPaid: boolean; otMin: string; otAmt: string; memo: string; days: number;
};
type AccForm = { mgr: string; from: string };
type VehForm = { from: string; mode: VehicleMode; vid: string; memo: string };   // [S3-P2h-2b] 차량 이용 이력
type DayForm = { date: string; vid: string; reason: DayReason; memo: string };   // [S3-P2h-2b] 그날 예외
type Props = {
  row: WorkerRow | null; // null = 새 인력
  workers: WorkerRow[];
  managers: ManagerRow[];
  isAdmin: boolean;
  justCreated?: boolean;
  onChanged: (id: number, created?: boolean) => Promise<void>;
  onClose: () => void;
};
type Period = { from: string; to: string | null; state: "future" | "current" | "past" };

const INCOMES = Object.keys(INCOME_LABEL) as IncomeType[];
const toMin = (s: string) => {
  const m = /^(\d{1,2}):(\d{2})/.exec(s);
  return m ? Number(m[1]) * 60 + Number(m[2]) : NaN;
};
const dayBefore = (iso: string) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
};

/** 최신순 시작일 목록 → 기간(다음 이력 전날까지)·상태 */
function periods(starts: string[], today: string): Period[] {
  let found = false;
  return starts.map((from, i) => {
    const to = i === 0 ? null : dayBefore(starts[i - 1]);
    let state: Period["state"] = "past";
    if (from > today) state = "future";
    else if (!found) { state = "current"; found = true; }
    return { from, to, state };
  });
}
function StateChip({ s }: { s: Period["state"] }) {
  if (s === "current") return <Chip tone="ok">현재 적용</Chip>;
  if (s === "future") return <Chip tone="warn">예정</Chip>;
  return <Chip>종료</Chip>;
}

const toForm = (r: WorkerRate | null, from: string, defVat: boolean, memo = ""): RateForm => ({
  amount: r ? String(r.amount) : "", from, vat: r ? r.vat_applied : defVat,
  ws: r?.work_start ?? "07:00", we: r?.work_end ?? "13:00",
  brk: String(r?.break_min ?? 0), brkPaid: r?.break_paid ?? true,
  otMin: r?.ot_unit_min ? String(r.ot_unit_min) : "", otAmt: r?.ot_unit_amount ? String(r.ot_unit_amount) : "",
  memo, days: r?.work_days ?? 31,
});

export default function WorkerEditor({ row, workers, managers, isAdmin, justCreated, onChanged, onClose }: Props) {
  const isNew = row === null;
  const today = todayKst();
  const [tab, setTab] = useState<Tab>(justCreated ? "rate" : "basic");
  const [detail, setDetail] = useState<WorkerDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<Tab | null>(null);
  const [note, setNote] = useState<SaveNoteState<Tab> | null>(
    justCreated ? { sec: "rate", ok: true, text: "등록됨 · 이어서 계약 조건을 입력하세요", at: nowHms() } : null);
  const [hl, setHl] = useState<number | null>(null); // 방금 저장한 이력 행

  // 기본
  const [name, setName] = useState(row?.name ?? "");
  const [income, setIncome] = useState<IncomeType>(row?.income_type ?? "employee");
  const [active, setActive] = useState(row?.active ?? true);
  const [memo, setMemo] = useState(row?.memo ?? "");
  const [endDate, setEndDate] = useState(row?.end_date ?? "");          // [S2-P0c] 퇴사일
  const [lastFull, setLastFull] = useState(row?.last_pay_full ?? true); // 정규직 마지막 달 월급 그대로
  const [lastAmt, setLastAmt] = useState(row?.last_pay_amount != null ? String(row.last_pay_amount) : "");

  // 계약 (저장된 구분 기준 — 서버도 저장된 구분으로 검증)
  const payType = INCOME_PAY[row?.income_type ?? income];
  const hourly = payType === "hourly";
  const [rMode, setRMode] = useState<Mode>(justCreated ? { kind: "add" } : null);
  const [rf, setRf] = useState<RateForm>(() => toForm(null, today, row?.income_type === "business"));
  const setR = (p: Partial<RateForm>) => setRf((f) => ({ ...f, ...p }));

  // 계정
  const [aMode, setAMode] = useState<Mode>(null);
  const [af, setAf] = useState<AccForm>({ mgr: "", from: today });

  // [S3-P2h-2b] 차량 이용 이력 · 그날 예외
  const [vdata, setVdata] = useState<WorkerVehicles | null>(null);
  const [cars, setCars] = useState<Vehicle[]>([]);
  const [vMode, setVMode] = useState<Mode>(null);
  const [vf, setVf] = useState<VehForm>({ from: today, mode: "company", vid: "", memo: "" });
  const [dOpen, setDOpen] = useState(false);
  const [df, setDf] = useState<DayForm>({ date: today, vid: "", reason: "swap", memo: "" });

  const load = async () => {
    if (!row) return;
    const [d, v] = await Promise.all([api.getWorker(row.id), api.getWorkerVehicles(row.id)]);
    setDetail(d);
    setVdata(v);
  };
  useEffect(() => {
    load().catch((e) => setError(errText(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row?.id]);
  useEffect(() => {
    if (row) listVehicles().then((r) => setCars(r.items)).catch(() => setCars([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row?.id]);

  const rates = detail?.rates ?? [];
  const accounts = detail?.accounts ?? [];
  const ratePeriods = useMemo(() => periods(rates.map((r) => r.effective_from), today), [rates, today]);
  const accPeriods = useMemo(() => periods(accounts.map((a) => a.start_date), today), [accounts, today]);
  const curRate = rates[ratePeriods.findIndex((p) => p.state === "current")] ?? null;
  const curAcc = accounts[accPeriods.findIndex((p) => p.state === "current")] ?? null;
  const editRateId = rMode?.kind === "edit" ? rMode.id : null;
  const editAccId = aMode?.kind === "edit" ? aMode.id : null;
  const editingRate = editRateId != null ? rates.find((r) => r.id === editRateId) ?? null : null;
  const editingAcc = editAccId != null ? accounts.find((a) => a.id === editAccId) ?? null : null;
  const vHist = vdata?.history ?? [];
  const vDays = vdata?.days ?? [];
  const vPeriods = useMemo(() => periods(vHist.map((h) => h.start_date), today), [vHist, today]);
  const editVehId = vMode?.kind === "edit" ? vMode.id : null;
  const editingVeh = editVehId != null ? vHist.find((h) => h.id === editVehId) ?? null : null;
  const carOptions = useMemo(() => [...cars].sort((a, b) =>
    Number(b.active) - Number(a.active) || a.plate_no.localeCompare(b.plate_no, "ko", { numeric: true })), [cars]);
  const carText = (c: Vehicle) =>
    `${c.plate_no} · ${FUEL_LABEL[c.fuel_type]}${c.model ? ` · ${c.model}` : ""}${c.active ? "" : " (사용 안 함)"}`;

  async function run(sec: Tab, okText: string, fn: () => Promise<{ id?: number } | void>, after?: () => void) {
    if (!row) return;
    const id = row.id;
    setBusy(sec);
    setError("");
    setNote(null);
    let res: { id?: number } | void = undefined;
    try {
      res = await fn();
    } catch (e) {
      setError(errText(e));
      setNote({ sec, ok: false, text: "저장 실패", at: nowHms() });
      setBusy(null);
      return;
    }
    if (sec !== "basic") setHl(res && res.id != null ? res.id : null);
    after?.();
    try {
      await Promise.all([load(), onChanged(id)]);
      setNote({ sec, ok: true, text: okText, at: nowHms() });
    } catch {
      setNote({ sec, ok: true, text: `${okText} (화면 새로고침 실패 — F5로 확인)`, at: nowHms() });
    } finally {
      setBusy(null);
    }
  }

  /* ---------- 기본 ---------- */
  const basicDirty = isNew
    ? name.trim() !== ""
    : name.trim() !== row.name || income !== row.income_type || active !== row.active ||
      memo.trim() !== (row.memo ?? "").trim() ||
      (!active && (endDate !== (row.end_date ?? "") || lastFull !== row.last_pay_full ||
        lastAmt !== (row.last_pay_amount != null ? String(row.last_pay_amount) : "")));

  async function saveBasic() {
    if (!name.trim()) return setError("이름을 입력하세요");
    const lastNum = lastAmt.trim() ? parseAmount(lastAmt) : NaN;
    if (!active && !endDate) return setError("비활성(퇴사·중단)으로 바꾸려면 퇴사일을 입력하세요 — 퇴사일까지의 물류비 이력은 그대로 남습니다");
    if (!active && income === "regular" && !lastFull && (Number.isNaN(lastNum) || lastNum < 0)) {
      return setError("마지막 달 지급액을 숫자로 입력하세요 (월급 그대로면 '월급 그대로 지급'을 체크)");
    }
    const body = {
      name: name.trim(), income_type: income, active, memo: memo.trim() || null,
      end_date: active ? null : endDate,
      last_pay_full: active || income !== "regular" ? true : lastFull,
      last_pay_amount: !active && income === "regular" && !lastFull ? lastNum : null,
    };
    if (row === null) {
      setBusy("basic");
      setError("");
      try {
        const res = await api.createWorker(body);
        if (res.id != null) await onChanged(res.id, true); // 편집 모드로 다시 열림
      } catch (e) {
        setError(errText(e));
        setNote({ sec: "basic", ok: false, text: "등록 실패", at: nowHms() });
      } finally {
        setBusy(null);
      }
      return;
    }
    const id = row.id;
    run("basic", "저장됨", () => api.updateWorker(id, body));
  }

  /* ---------- 계약 ---------- */
  const amt = parseAmount(rf.amount);
  const okAmt = !Number.isNaN(amt) && amt > 0;
  const span = toMin(rf.we) - toMin(rf.ws);
  const brkMin = Number(rf.brk) || 0;
  const paidMin = span > 0 ? (rf.brkPaid ? span : Math.max(0, span - brkMin)) : 0;
  const um = Number(rf.otMin) || 0;
  const ua = rf.otAmt.trim() ? parseAmount(rf.otAmt) : 0;
  const dailyBase = okAmt && hourly ? Math.round((amt * paidMin) / 60) : 0;
  const hourOt = okAmt && hourly ? Math.round(amt) + (um > 0 && ua > 0 ? Math.floor(60 / um) * ua : 0) : 0;
  const ratePast = rMode != null && (rf.from <= today || (editingRate != null && editingRate.effective_from <= today));

  function openRateAdd() {
    setError("");
    setNote(null);
    setRf(toForm(curRate ?? rates[0] ?? null, today, row?.income_type === "business"));
    setRMode({ kind: "add" });
  }
  function openRateEdit(r: WorkerRate) {
    setError("");
    setNote(null);
    setRf(toForm(r, r.effective_from, false, r.memo ?? ""));
    setRMode({ kind: "edit", id: r.id });
  }

  function saveRate() {
    if (!row || !rMode) return;
    if (!rf.from) return setError("적용 시작일을 입력하세요");
    if (rates.some((r) => r.effective_from === rf.from && r.id !== editRateId)) {
      return setError(`${rf.from}에 시작하는 계약이 이미 있습니다. 이력에서 그 행의 [수정]을 누르세요`);
    }
    if (!okAmt) return setError("금액을 숫자로 입력하세요");
    if (Number.isNaN(ua)) return setError("초과수당 금액을 숫자로 입력하세요");
    if (hourly) {
      if (!(span > 0)) return setError("지정 퇴근은 지정 출근보다 늦어야 합니다");
      if (brkMin < 0 || brkMin >= span) return setError("휴게시간을 확인하세요");
      if ((um > 0) !== (ua > 0)) return setError("초과수당 단위(분)와 금액은 둘 다 입력하거나 둘 다 비워 두세요");
      if (rf.days === 0) return setError("근무 요일을 하나 이상 선택하세요");
    }
    const body: WorkerRateInput = {
      effective_from: rf.from, pay_type: payType, amount: amt, vat_applied: rf.vat, memo: rf.memo.trim() || null,
      ...(hourly ? { work_start: rf.ws, work_end: rf.we, break_min: brkMin, break_paid: rf.brkPaid, work_days: rf.days,
        ot_unit_min: um, ot_unit_amount: ua } : {}),
    };
    const id = row.id;
    const rid = editRateId;
    run("rate", rid != null ? `계약 수정됨 (${rf.from}부터)` : `계약 추가됨 (${rf.from}부터)`,
      () => (rid != null ? api.updateWorkerRate(rid, body) : api.addWorkerRate(id, body)),
      () => setRMode(null));
  }
  const delRate = (r: WorkerRate) => {
    if (!window.confirm(`${r.effective_from} 시작 계약을 삭제할까요?\n삭제하면 그 기간은 직전 계약 조건으로 계산됩니다.`)) return;
    run("rate", "계약 이력 삭제됨", () => api.deleteWorkerRate(r.id));
  };

  /* ---------- 계정 ---------- */
  const holders = useMemo(() => {
    const m = new Map<number, string>();
    workers.forEach((w) => {
      if (w.active && w.account?.manager_id != null && w.id !== row?.id) m.set(w.account.manager_id, w.name);
    });
    return m;
  }, [workers, row?.id]);
  const mgrOptions = useMemo(() => [...managers].sort((a, b) =>
    Number(b.ops_status === "active") - Number(a.ops_status === "active") ||
    (a.name ?? "").localeCompare(b.name ?? "", "ko", { numeric: true })), [managers]);

  function openAccAdd() {
    setError("");
    setNote(null);
    setAf({ mgr: curAcc?.manager_id != null ? String(curAcc.manager_id) : "", from: today });
    setAMode({ kind: "add" });
  }
  function openAccEdit(a: WorkerAccount) {
    setError("");
    setNote(null);
    setAf({ mgr: a.manager_id != null ? String(a.manager_id) : "", from: a.start_date });
    setAMode({ kind: "edit", id: a.id });
  }
  function saveAcc() {
    if (!row || !aMode) return;
    if (!af.from) return setError("시작일을 입력하세요");
    if (accounts.some((a) => a.start_date === af.from && a.id !== editAccId)) {
      return setError(`${af.from}에 시작하는 계정 이력이 이미 있습니다. 이력에서 그 행의 [수정]을 누르세요`);
    }
    const body = { manager_id: af.mgr ? Number(af.mgr) : null, start_date: af.from };
    const id = row.id;
    const aid = editAccId;
    run("account", aid != null ? `계정 이력 수정됨 (${af.from}부터)` : `고정 계정 저장됨 (${af.from}부터)`,
      () => (aid != null ? api.updateWorkerAccount(aid, body) : api.assignWorkerAccount(id, body)),
      () => setAMode(null));
  }
  const delAcc = (a: WorkerAccount) => {
    if (!window.confirm(`${a.start_date} 시작 계정 이력을 삭제할까요?`)) return;
    run("account", "계정 이력 삭제됨", () => api.deleteWorkerAccount(a.id));
  };

  /* ---------- 차량 이용 [S3-P2h-2b] ---------- */
  function openVehAdd() {
    setError("");
    setNote(null);
    const cur = vHist[vPeriods.findIndex((p) => p.state === "current")] ?? null;
    setVf({ from: today, mode: cur?.mode ?? "company", vid: cur?.vehicle_id != null ? String(cur.vehicle_id) : "", memo: "" });
    setVMode({ kind: "add" });
  }
  function openVehEdit(h: WorkerVehicle) {
    setError("");
    setNote(null);
    setVf({ from: h.start_date, mode: h.mode, vid: h.vehicle_id != null ? String(h.vehicle_id) : "", memo: h.memo ?? "" });
    setVMode({ kind: "edit", id: h.id });
  }
  function saveVeh() {
    if (!row || !vMode) return;
    if (!vf.from) return setError("시작일을 입력하세요");
    if (vf.mode === "company" && !vf.vid) return setError("회사 차량은 차량을 선택하세요");
    if (vHist.some((h) => h.start_date === vf.from && h.id !== editVehId)) {
      return setError(`${vf.from}에 시작하는 차량 이용 이력이 이미 있습니다. 이력에서 그 행의 [수정]을 누르세요`);
    }
    const body = {
      start_date: vf.from, mode: vf.mode, vehicle_id: vf.mode === "company" ? Number(vf.vid) : null,
      memo: vf.memo.trim() || null,
    };
    const id = row.id;
    const hid = editVehId;
    run("vehicle", hid != null ? `차량 이용 이력 수정됨 (${vf.from}부터)` : `차량 이용 이력 추가됨 (${vf.from}부터)`,
      () => (hid != null ? api.updateWorkerVehicle(hid, body) : api.addWorkerVehicle(id, body)),
      () => setVMode(null));
  }
  const delVeh = (h: WorkerVehicle) => {
    if (!window.confirm(`${h.start_date} 시작 차량 이용 이력을 삭제할까요?\n삭제하면 그 기간은 직전 이력으로 계산됩니다.`)) return;
    run("vehicle", "차량 이용 이력 삭제됨", () => api.deleteWorkerVehicle(h.id));
  };
  function openDayAdd() {
    setError("");
    setNote(null);
    setDf({ date: today, vid: "", reason: "swap", memo: "" });
    setDOpen(true);
  }
  function saveDay() {
    if (!row) return;
    if (!df.date) return setError("날짜를 입력하세요");
    if (vDays.some((d) => d.work_date === df.date)) {
      return setError(`${df.date} 그날 예외가 이미 있습니다. 삭제한 뒤 다시 입력하세요`);
    }
    const body = { work_date: df.date, vehicle_id: df.vid ? Number(df.vid) : null, reason: df.reason, memo: df.memo.trim() || null };
    const id = row.id;
    run("vehicle", `그날 예외 추가됨 (${df.date})`, () => api.addWorkerVehicleDay(id, body),
      () => { setDOpen(false); setHl(null); });
  }
  const delDay = (d: WorkerVehicleDay) => {
    if (!window.confirm(`${d.work_date} 그날 예외를 삭제할까요?\n삭제하면 그날은 차량 이용 이력대로 계산됩니다.`)) return;
    run("vehicle", "그날 예외 삭제됨", () => api.deleteWorkerVehicleDay(d.id), () => setHl(null));
  };

  function close() {
    if (basicDirty || rMode || aMode || vMode || dOpen) {
      if (!window.confirm("저장하지 않은 입력이 있습니다. 닫을까요?")) return;
    }
    onClose();
  }
  const label = (s: Tab, idle: string) => (busy === s ? "저장 중…" : idle);
  const locked = busy !== null;

  const TABS: Array<[Tab, string, boolean]> = [
    ["basic", "기본 정보", false],
    ["rate", `계약 조건 ${rates.length}`, rMode !== null],
    ["account", `고정 계정 ${accounts.length}`, aMode !== null],
    ["vehicle", `차량 이용 ${vHist.length}`, vMode !== null || dOpen],
  ];

  return (
    <Modal
      open
      size="xl"
      onClose={close}
      title={isNew ? "인력 추가" : <>{row.name} <span className="muted small">{INCOME_LABEL[row.income_type]}</span></>}
      footer={<Button onClick={close}>닫기</Button>}
    >
      {!isNew && (
        <div className="seg ed-tabs">
          {TABS.map(([k, l, open]) => (
            <button key={k} type="button" className={tab === k ? "on" : undefined} onClick={() => setTab(k)}
              title={open ? "입력 중인 폼이 있습니다" : undefined}>
              {l}{open ? " ●" : ""}
            </button>
          ))}
        </div>
      )}
      {error && <div className="stack"><ErrorBox message={error} /></div>}

      {/* ---------- 기본 정보 ---------- */}
      {(isNew || tab === "basic") && (
        <>
          {row && needsName(row) && (
            <div className="stack">
              <Chip tone="caution">
                이전 매니저 급여 자료에서 옮겨진 인력입니다{row.account?.manager_name ? ` (계정: ${row.account.manager_name})` : ""}. 실제 이름으로 바꿔 주세요
              </Chip>
            </div>
          )}
          {isAdmin ? (
            <div className="form-grid">
              <label className="field">이름
                <input className="input" value={name} maxLength={50} onChange={(e) => setName(e.target.value)} placeholder="예: 홍길동" />
              </label>
              <label className="field">소득 구분
                <select className="input" value={income} onChange={(e) => setIncome(e.target.value as IncomeType)}>
                  {INCOMES.map((k) => <option key={k} value={k}>{INCOME_LABEL[k]}{k === "regular" ? " (월급)" : " (시급)"}</option>)}
                </select>
              </label>
              <label className="field">상태
                <select className="input" value={active ? "1" : "0"} onChange={(e) => setActive(e.target.value === "1")}>
                  <option value="1">활성</option>
                  <option value="0">비활성 (퇴사·중단)</option>
                </select>
              </label>
              {!active && (
                <>
                  <label className="field">퇴사일
                    <input type="date" className="input" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                  </label>
                  {income === "regular" && (
                    <div className="field">마지막 달 월급
                      <label className={`wd-chk${lastFull ? " on" : ""}`}>
                        <input type="checkbox" checked={lastFull} onChange={(e) => setLastFull(e.target.checked)} /> 월급 그대로 지급
                      </label>
                    </div>
                  )}
                  {income === "regular" && !lastFull && (
                    <label className="field">마지막 달 지급액(원)
                      <input className="input" inputMode="numeric" value={lastAmt} onChange={(e) => setLastAmt(e.target.value)} placeholder="예: 1,500,000" />
                    </label>
                  )}
                  <span className="muted small field-wide">
                    퇴사일까지의 물류비 인건비는 그대로 남고, 다음 날부터 0원{income === "regular" ? " · 퇴사 달은 1일~퇴사일 영업일로 나눔" : " · 근무표 기준"}
                  </span>
                </>
              )}
              <label className="field field-wide">메모
                <input className="input" value={memo} maxLength={500} onChange={(e) => setMemo(e.target.value)} />
              </label>
              <div className="form-actions">
                {!isNew && income !== row.income_type && (
                  <Chip tone="caution">구분 변경: 기존 계약 이력은 그대로, 새 계약부터 {INCOME_PAY[income] === "monthly" ? "월급제" : "시급제"}</Chip>
                )}
                {!isNew && basicDirty && <Chip tone="caution">변경됨 · 저장 전</Chip>}
                <SaveNote note={note} sec="basic" hide={!isNew && basicDirty} />
                <Button variant="primary" disabled={locked || !basicDirty} onClick={saveBasic}>
                  {label("basic", isNew ? "등록" : basicDirty ? "저장" : "저장됨")}
                </Button>
              </div>
            </div>
          ) : row && (
            <div className="muted small">{INCOME_LABEL[row.income_type]} · {row.active ? "활성" : `비활성${row.end_date ? ` (퇴사 ${row.end_date})` : ""}`} · {row.memo || "메모 없음"}</div>
          )}
          {isNew && <p className="muted small">등록 후 계약 조건과 고정 계정을 입력할 수 있습니다.</p>}
        </>
      )}

      {/* ---------- 계약 조건 ---------- */}
      {row && tab === "rate" && (
        <>
          <section className="ed-hist">
            <div className="ed-head">
              <h3 className="sub-title">계약 이력 <span className="muted small">조회 · 시작일부터 다음 이력 전날까지 적용</span></h3>
              <div className="kv-line">
                <SaveNote note={note} sec="rate" />
                {isAdmin && <Button size="sm" variant="primary" disabled={locked || rMode !== null} onClick={openRateAdd}>+ 새 계약 추가</Button>}
              </div>
            </div>
            {!detail ? <Spinner /> : rates.length === 0 ? (
              <div className="muted small">입력된 계약 조건이 없습니다. [+ 새 계약 추가]로 입력하세요.</div>
            ) : (
              <DataTable columns={["상태", "적용 기간", "급여", "지정 근무", "초과수당", "부가세",
                { label: "계약 일 기본급", num: true }, "메모 · 입력자", ...(isAdmin ? ["관리"] : [])]}>
                {rates.map((r, i) => {
                  const p = ratePeriods[i];
                  const cls = [r.id === editRateId ? "ed-editing" : "", r.id === hl ? "row-new" : "",
                    p.state === "past" ? "off" : ""].filter(Boolean).join(" ");
                  return (
                    <tr key={r.id} className={cls || undefined}>
                      <td><StateChip s={p.state} /></td>
                      <td className="ed-nowrap">{p.from} ~ {p.to ?? ""}</td>
                      <td>{rateText(r)}</td>
                      <td>{workText(r)}</td>
                      <td>{r.pay_type === "hourly" ? otText(r) : "-"}</td>
                      <td>{r.vat_applied ? "포함" : "-"}</td>
                      <td className="num">{r.daily_base != null ? won(r.daily_base) : "-"}</td>
                      <td className="small">{r.memo ?? ""}<div className="muted">{r.created_by ?? ""}</div></td>
                      {isAdmin && (
                        <td className="ed-nowrap">
                          <Button size="sm" disabled={locked || rMode !== null} onClick={() => openRateEdit(r)}>수정</Button>{" "}
                          <Button size="sm" variant="danger" disabled={locked || rMode !== null} onClick={() => delRate(r)}>삭제</Button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </DataTable>
            )}
          </section>

          {isAdmin && rMode && (
            <section className={`ed-form ${rMode.kind === "edit" ? "is-edit" : "is-add"}`}>
              <div className="ed-head">
                <h3 className="sub-title">
                  {rMode.kind === "edit" ? `계약 수정 — ${editingRate?.effective_from ?? ""} 시작분` : "새 계약 추가"}
                </h3>
                <span className="muted small">
                  {rMode.kind === "edit"
                    ? "잘못 입력했거나 빠진 정보를 보완할 때. 이력의 이 행을 바꿉니다 (변경 기록은 남음)"
                    : "시급 인상·근무시간 변경 등 실제 조건이 바뀔 때. 이전 기간은 기존 조건 유지 · 현재 조건을 복사해 두었습니다"}
                </span>
              </div>
              <div className="form-grid">
                <label className="field">{hourly ? "시급(원)" : "월급(원)"}
                  <input className="input" inputMode="numeric" value={rf.amount} onChange={(e) => setR({ amount: e.target.value })}
                    placeholder={hourly ? "예: 16,000" : "예: 3,000,000"} />
                </label>
                <label className="field">적용 시작일
                  <input type="date" className="input" value={rf.from} onChange={(e) => setR({ from: e.target.value })} />
                </label>
                <label className="field">부가세
                  <select className="input" value={rf.vat ? "1" : "0"} onChange={(e) => setR({ vat: e.target.value === "1" })}>
                    <option value="0">미적용</option>
                    <option value="1">10% 가산</option>
                  </select>
                </label>
                {hourly && (
                  <>
                    <label className="field">지정 출근
                      <input type="time" className="input" value={rf.ws} onChange={(e) => setR({ ws: e.target.value })} />
                    </label>
                    <label className="field">지정 퇴근
                      <input type="time" className="input" value={rf.we} onChange={(e) => setR({ we: e.target.value })} />
                    </label>
                    <label className="field">휴게(분)
                      <input className="input" inputMode="numeric" value={rf.brk} onChange={(e) => setR({ brk: e.target.value })} />
                    </label>
                    <label className="field">휴게 처리
                      <select className="input" value={rf.brkPaid ? "1" : "0"} onChange={(e) => setR({ brkPaid: e.target.value === "1" })}>
                        <option value="1">유급 (근무시간에 포함)</option>
                        <option value="0">무급 (근무시간에서 차감)</option>
                      </select>
                    </label>
                    <div className="field field-wide">근무 요일
                      <span className="muted small"> 기본 월~금 · 체크 안 한 요일도 근무 입력 가능 (토·일 근무는 주말 근무로 분류)</span>
                      <div className="wd-pick">
                        {DAY_BITS.map(([b, l]) => (
                          <label key={b} className={`wd-chk${rf.days & b ? " on" : ""}`}>
                            <input type="checkbox" checked={(rf.days & b) !== 0} onChange={() => setR({ days: rf.days ^ b })} /> {l}
                          </label>
                        ))}
                      </div>
                    </div>
                    <label className="field">초과수당 단위(분)
                      <input className="input" inputMode="numeric" value={rf.otMin} onChange={(e) => setR({ otMin: e.target.value })} placeholder="예: 30 (비우면 없음)" />
                    </label>
                    <label className="field">단위당 금액(원)
                      <input className="input" inputMode="numeric" value={rf.otAmt} onChange={(e) => setR({ otAmt: e.target.value })} placeholder="예: 5,000" />
                    </label>
                  </>
                )}
                <label className="field field-wide">메모
                  <input className="input" value={rf.memo} maxLength={200} onChange={(e) => setR({ memo: e.target.value })} />
                </label>
              </div>
              {ratePast && (
                <div className="stack">
                  <Chip tone="caution">오늘 이전부터 적용되는 계약입니다. 저장하면 그 기간 기본급·초과수당·예상 물류비가 이 조건으로 다시 계산됩니다</Chip>
                </div>
              )}
              <div className="form-actions">
                {hourly && paidMin > 0 && okAmt && (
                  <span className="muted small">
                    계약 {hm(paidMin)} × {won(amt)} = 일 기본급 {won(dailyBase)}
                    {" · "}지정 시간 밖 1시간 근무 시 {won(hourOt)}
                    {um > 0 && ua > 0 ? ` (시급 ${won(amt)} + 초과수당 ${won(hourOt - Math.round(amt))})` : " (초과수당 없음)"}
                  </span>
                )}
                {!hourly && okAmt && <span className="muted small">월 {won(amt)} + 인센티브(월 입력)</span>}
                <Button disabled={locked} onClick={() => setRMode(null)}>취소</Button>
                <Button variant="primary" disabled={locked} onClick={saveRate}>
                  {label("rate", rMode.kind === "edit" ? "수정 저장" : "계약 추가")}
                </Button>
              </div>
            </section>
          )}
          <p className="muted small">
            기본급 = 시급 × 월 전체 유급 시간(초과 포함, 엑셀 월급여와 동일). 초과수당 = 날짜별 지정 시간 밖 근무를 단위(분)마다 지정 금액, 단위 미만 버림.
            출근은 지문이 지정 시각보다 빨라도 지정 시각으로 인정합니다.
          </p>
        </>
      )}

      {/* ---------- 고정 계정 ---------- */}
      {row && tab === "account" && (
        <>
          <section className="ed-hist">
            <div className="ed-head">
              <h3 className="sub-title">고정 계정 이력 <span className="muted small">조회 · 하루만 바뀌는 경우는 근무 입력에서 일 단위 예외로 처리</span></h3>
              <div className="kv-line">
                <SaveNote note={note} sec="account" />
                {isAdmin && <Button size="sm" variant="primary" disabled={locked || aMode !== null} onClick={openAccAdd}>+ 계정 변경 추가</Button>}
              </div>
            </div>
            {!detail ? <Spinner /> : accounts.length === 0 ? (
              <div className="muted small">배정된 계정이 없습니다. [+ 계정 변경 추가]로 입력하세요.</div>
            ) : (
              <DataTable columns={["상태", "적용 기간", "계정", "입력자", ...(isAdmin ? ["관리"] : [])]}>
                {accounts.map((a, i) => {
                  const p = accPeriods[i];
                  const cls = [a.id === editAccId ? "ed-editing" : "", a.id === hl ? "row-new" : "",
                    p.state === "past" ? "off" : ""].filter(Boolean).join(" ");
                  return (
                    <tr key={a.id} className={cls || undefined}>
                      <td><StateChip s={p.state} /></td>
                      <td className="ed-nowrap">{p.from} ~ {p.to ?? ""}</td>
                      <td>{a.manager_id != null
                        ? <><span className="dot" style={{ background: a.manager_color ?? "#9ca3af" }} /> {a.manager_name ?? `#${a.manager_id}`}</>
                        : "계정 없음"}</td>
                      <td className="muted small">{a.created_by ?? "-"}</td>
                      {isAdmin && (
                        <td className="ed-nowrap">
                          <Button size="sm" disabled={locked || aMode !== null} onClick={() => openAccEdit(a)}>수정</Button>{" "}
                          <Button size="sm" variant="danger" disabled={locked || aMode !== null} onClick={() => delAcc(a)}>삭제</Button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </DataTable>
            )}
          </section>

          {isAdmin && aMode && (
            <section className={`ed-form ${aMode.kind === "edit" ? "is-edit" : "is-add"}`}>
              <div className="ed-head">
                <h3 className="sub-title">
                  {aMode.kind === "edit" ? `계정 이력 수정 — ${editingAcc?.start_date ?? ""} 시작분` : "계정 변경 추가"}
                </h3>
                <span className="muted small">
                  {aMode.kind === "edit" ? "계정이나 시작일을 잘못 입력했을 때" : "시작일부터 이 계정을 고정 사용 (이전 기간은 기존 계정 유지)"}
                </span>
              </div>
              <div className="form-grid">
                <label className="field field-wide">계정
                  <select className="input" value={af.mgr} onChange={(e) => setAf((f) => ({ ...f, mgr: e.target.value }))}>
                    <option value="">계정 없음</option>
                    {mgrOptions.map((m) => (
                      <option key={m.manager_id} value={m.manager_id}>
                        {m.name ?? `#${m.manager_id}`}
                        {m.ops_status !== "active" ? " (운영 비활성)" : ""}
                        {holders.has(m.manager_id) ? ` · 현재 ${holders.get(m.manager_id)}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">시작일
                  <input type="date" className="input" value={af.from} onChange={(e) => setAf((f) => ({ ...f, from: e.target.value }))} />
                </label>
              </div>
              <div className="form-actions">
                <Button disabled={locked} onClick={() => setAMode(null)}>취소</Button>
                <Button variant="primary" disabled={locked} onClick={saveAcc}>
                  {label("account", aMode.kind === "edit" ? "수정 저장" : "계정 저장")}
                </Button>
              </div>
            </section>
          )}
        </>
      )}

      {/* ---------- 차량 이용 [S3-P2h-2b] ---------- */}
      {row && tab === "vehicle" && (
        <>
          <p className="muted small">
            물류비의 차량비·유류비는 날짜별로 <b>계정 → 그날 담당 인력 → 그 인력의 차량</b>으로 나눕니다.
            이력이 없는 날은 기존 계정 차량 배정을 씁니다. 유류비가 마감된 달에 걸리는 이력·예외는 바꿀 수 없습니다.
            {row.end_date ? ` 퇴사일(${row.end_date}) 뒤로는 계산에 쓰이지 않습니다.` : ""}
          </p>
          <section className="ed-hist">
            <div className="ed-head">
              <h3 className="sub-title">차량 이용 이력 <span className="muted small">시작일부터 다음 이력 전날까지 적용</span></h3>
              <div className="kv-line">
                <SaveNote note={note} sec="vehicle" />
                {isAdmin && <Button size="sm" variant="primary" disabled={locked || vMode !== null || dOpen} onClick={openVehAdd}>+ 차량 변경 추가</Button>}
              </div>
            </div>
            {!vdata ? <Spinner /> : vHist.length === 0 ? (
              <div className="muted small">차량 이용 이력이 없습니다. 지금은 기존 계정 차량 배정으로 계산됩니다.</div>
            ) : (
              <DataTable columns={["상태", "적용 기간", "이용 구분", "차량", "메모 · 입력자", ...(isAdmin ? ["관리"] : [])]}>
                {vHist.map((h, i) => {
                  const p = vPeriods[i];
                  const cls = [h.id === editVehId ? "ed-editing" : "", h.id === hl ? "row-new" : "",
                    p.state === "past" ? "off" : ""].filter(Boolean).join(" ");
                  return (
                    <tr key={h.id} className={cls || undefined}>
                      <td><StateChip s={p.state} /></td>
                      <td className="ed-nowrap">{p.from} ~ {p.to ?? ""}</td>
                      <td>{VEHICLE_MODE_LABEL[h.mode]}</td>
                      <td>{h.plate_no ?? "-"}</td>
                      <td className="small">{h.memo ?? ""}<div className="muted">{h.created_by ?? ""}</div></td>
                      {isAdmin && (
                        <td className="ed-nowrap">
                          <Button size="sm" disabled={locked || vMode !== null || dOpen} onClick={() => openVehEdit(h)}>수정</Button>{" "}
                          <Button size="sm" variant="danger" disabled={locked || vMode !== null || dOpen} onClick={() => delVeh(h)}>삭제</Button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </DataTable>
            )}
          </section>

          {isAdmin && vMode && (
            <section className={`ed-form ${vMode.kind === "edit" ? "is-edit" : "is-add"}`}>
              <div className="ed-head">
                <h3 className="sub-title">
                  {vMode.kind === "edit" ? `차량 이용 이력 수정 — ${editingVeh?.start_date ?? ""} 시작분` : "차량 변경 추가"}
                </h3>
                <span className="muted small">
                  {vMode.kind === "edit"
                    ? "차량이나 시작일을 잘못 입력했을 때 (변경 기록은 남음)"
                    : "시작일부터 이 차량을 계속 사용 (이전 기간은 기존 이력 유지) · 하루만 바뀌면 아래 '그날 예외'"}
                </span>
              </div>
              <div className="form-grid">
                <label className="field">이용 구분
                  <select className="input" value={vf.mode} onChange={(e) => setVf((f) => ({ ...f, mode: e.target.value as VehicleMode }))}>
                    {(Object.keys(VEHICLE_MODE_LABEL) as VehicleMode[]).map((k) => (
                      <option key={k} value={k}>{VEHICLE_MODE_LABEL[k]}</option>
                    ))}
                  </select>
                </label>
                {vf.mode === "company" && (
                  <label className="field">차량
                    <select className="input" value={vf.vid} onChange={(e) => setVf((f) => ({ ...f, vid: e.target.value }))}>
                      <option value="">선택</option>
                      {carOptions.map((c) => <option key={c.id} value={c.id}>{carText(c)}</option>)}
                    </select>
                  </label>
                )}
                <label className="field">시작일
                  <input type="date" className="input" value={vf.from} onChange={(e) => setVf((f) => ({ ...f, from: e.target.value }))} />
                </label>
                <label className="field field-wide">메모
                  <input className="input" value={vf.memo} maxLength={200} onChange={(e) => setVf((f) => ({ ...f, memo: e.target.value }))} />
                </label>
              </div>
              {vf.mode !== "company" && (
                <div className="stack">
                  <Chip tone="caution">자차·차량 없음 기간에는 이 인력이 담당한 계정에 회사 차량비·유류비가 배정되지 않습니다</Chip>
                </div>
              )}
              <div className="form-actions">
                <Button disabled={locked} onClick={() => setVMode(null)}>취소</Button>
                <Button variant="primary" disabled={locked} onClick={saveVeh}>
                  {label("vehicle", vMode.kind === "edit" ? "수정 저장" : "이력 저장")}
                </Button>
              </div>
            </section>
          )}

          <section className="ed-hist">
            <div className="ed-head">
              <h3 className="sub-title">그날 예외 <span className="muted small">고장·교대 등으로 하루만 다른 차량을 쓴 날 (같은 날 두 사람이 같은 차량을 써도 됨)</span></h3>
              {isAdmin && <Button size="sm" variant="primary" disabled={locked || vMode !== null || dOpen} onClick={openDayAdd}>+ 그날 예외 추가</Button>}
            </div>
            {!vdata ? <Spinner /> : vDays.length === 0 ? (
              <div className="muted small">그날 예외가 없습니다.</div>
            ) : (
              <DataTable columns={["날짜", "차량", "사유", "메모 · 입력자", ...(isAdmin ? ["관리"] : [])]}>
                {vDays.map((d) => (
                  <tr key={d.id}>
                    <td className="ed-nowrap">{d.work_date}</td>
                    <td>{d.plate_no ?? "회사 차량 없음"}</td>
                    <td>{DAY_REASON_LABEL[d.reason]}</td>
                    <td className="small">{d.memo ?? ""}<div className="muted">{d.created_by ?? ""}</div></td>
                    {isAdmin && (
                      <td className="ed-nowrap">
                        <Button size="sm" variant="danger" disabled={locked || vMode !== null || dOpen} onClick={() => delDay(d)}>삭제</Button>
                      </td>
                    )}
                  </tr>
                ))}
              </DataTable>
            )}
          </section>

          {isAdmin && dOpen && (
            <section className="ed-form is-add">
              <div className="ed-head">
                <h3 className="sub-title">그날 예외 추가</h3>
                <span className="muted small">그날만 이 차량으로 계산 · 차량을 비우면 그날은 회사 차량 없음</span>
              </div>
              <div className="form-grid">
                <label className="field">날짜
                  <input type="date" className="input" value={df.date} onChange={(e) => setDf((f) => ({ ...f, date: e.target.value }))} />
                </label>
                <label className="field">차량
                  <select className="input" value={df.vid} onChange={(e) => setDf((f) => ({ ...f, vid: e.target.value }))}>
                    <option value="">회사 차량 없음</option>
                    {carOptions.map((c) => <option key={c.id} value={c.id}>{carText(c)}</option>)}
                  </select>
                </label>
                <label className="field">사유
                  <select className="input" value={df.reason} onChange={(e) => setDf((f) => ({ ...f, reason: e.target.value as DayReason }))}>
                    {(Object.keys(DAY_REASON_LABEL) as DayReason[]).map((k) => (
                      <option key={k} value={k}>{DAY_REASON_LABEL[k]}</option>
                    ))}
                  </select>
                </label>
                <label className="field field-wide">메모
                  <input className="input" value={df.memo} maxLength={200} onChange={(e) => setDf((f) => ({ ...f, memo: e.target.value }))} />
                </label>
              </div>
              <div className="form-actions">
                <Button disabled={locked} onClick={() => setDOpen(false)}>취소</Button>
                <Button variant="primary" disabled={locked} onClick={saveDay}>{label("vehicle", "예외 저장")}</Button>
              </div>
            </section>
          )}
        </>
      )}
    </Modal>
  );
}
