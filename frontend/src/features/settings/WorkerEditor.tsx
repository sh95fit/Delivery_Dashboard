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
import { INCOME_LABEL, INCOME_PAY, needsName, otText, rateText, workText } from "@/api/workers";
import type { IncomeType, WorkerDetail, WorkerRow } from "@/api/workers";
import type { ManagerRow } from "@/api/masters";
import { errText, parseAmount } from "@/lib/form";
import { hm, todayKst, won } from "@/lib/format";

type Sec = "basic" | "rate" | "account";
type Props = {
  row: WorkerRow | null; // null = 새 인력
  workers: WorkerRow[];
  managers: ManagerRow[];
  isAdmin: boolean;
  justCreated?: boolean;
  onChanged: (id: number, created?: boolean) => Promise<void>;
  onClose: () => void;
};

const INCOMES = Object.keys(INCOME_LABEL) as IncomeType[];
const toMin = (s: string) => {
  const m = /^(\d{1,2}):(\d{2})/.exec(s);
  return m ? Number(m[1]) * 60 + Number(m[2]) : NaN;
};

export default function WorkerEditor({ row, workers, managers, isAdmin, justCreated, onChanged, onClose }: Props) {
  const isNew = row === null;
  const cur = row?.rate ?? null;
  const [detail, setDetail] = useState<WorkerDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<Sec | null>(null);
  const [note, setNote] = useState<SaveNoteState<Sec> | null>(
    justCreated ? { sec: "basic", ok: true, text: "등록됨 · 이어서 계약 조건과 고정 계정을 입력하세요", at: nowHms() } : null);
  const [newRateId, setNewRateId] = useState<number | null>(null);
  const [newAccId, setNewAccId] = useState<number | null>(null);

  // 기본
  const [name, setName] = useState(row?.name ?? "");
  const [income, setIncome] = useState<IncomeType>(row?.income_type ?? "employee");
  const [active, setActive] = useState(row?.active ?? true);
  const [memo, setMemo] = useState(row?.memo ?? "");

  // 계약 (저장된 구분 기준 — 서버도 저장된 구분으로 검증)
  const payType = INCOME_PAY[row?.income_type ?? income];
  const hourly = payType === "hourly";
  const [amount, setAmount] = useState("");
  const [from, setFrom] = useState(todayKst());
  const [vat, setVat] = useState(cur ? cur.vat_applied : row?.income_type === "business");
  const [wStart, setWStart] = useState(cur?.work_start ?? "07:00");
  const [wEnd, setWEnd] = useState(cur?.work_end ?? "13:00");
  const [brk, setBrk] = useState(String(cur?.break_min ?? 0));
  const [brkPaid, setBrkPaid] = useState(cur?.break_paid ?? true);
  const [otMin, setOtMin] = useState(cur?.ot_unit_min ? String(cur.ot_unit_min) : "");
  const [otAmt, setOtAmt] = useState(cur?.ot_unit_amount ? String(cur.ot_unit_amount) : "");
  const [rateMemo, setRateMemo] = useState("");

  // 계정
  const [mgr, setMgr] = useState(row?.account?.manager_id != null ? String(row.account.manager_id) : "");
  const [accFrom, setAccFrom] = useState(todayKst());

  const load = async () => { if (row) setDetail(await api.getWorker(row.id)); };
  useEffect(() => {
    load().catch((e) => setError(errText(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row?.id]);

  async function run(id: number, sec: Sec, okText: string, fn: () => Promise<unknown>) {
    setBusy(sec);
    setError("");
    setNote(null);
    try {
      await fn();
    } catch (e) {
      setError(errText(e));
      setNote({ sec, ok: false, text: "저장 실패", at: nowHms() });
      setBusy(null);
      return;
    }
    try {
      await Promise.all([load(), onChanged(id)]);
      setNote({ sec, ok: true, text: okText, at: nowHms() });
    } catch {
      setNote({ sec, ok: true, text: `${okText} (화면 새로고침 실패 — F5로 확인)`, at: nowHms() });
    } finally {
      setBusy(null);
    }
  }

  const basicDirty = isNew
    ? name.trim() !== ""
    : name.trim() !== row.name || income !== row.income_type || active !== row.active ||
      memo.trim() !== (row.memo ?? "").trim();
  const rateDirty = amount.trim() !== "" || rateMemo.trim() !== "";

  async function saveBasic() {
    if (!name.trim()) return setError("이름을 입력하세요");
    const body = { name: name.trim(), income_type: income, active, memo: memo.trim() || null };
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
    run(id, "basic", "저장됨", () => api.updateWorker(id, body));
  }

  // 계약 미리보기
  const amt = parseAmount(amount);
  const okAmt = !Number.isNaN(amt) && amt > 0;
  const span = toMin(wEnd) - toMin(wStart);
  const brkMin = Number(brk) || 0;
  const paidMin = span > 0 ? (brkPaid ? span : Math.max(0, span - brkMin)) : 0;
  const um = Number(otMin) || 0;
  const ua = otAmt.trim() ? parseAmount(otAmt) : 0;
  const dailyBase = okAmt && hourly ? Math.round((amt * paidMin) / 60) : 0;
  const hourOt = okAmt && hourly ? Math.round(amt) + (um > 0 && ua > 0 ? Math.floor(60 / um) * ua : 0) : 0;

  function addRate() {
    if (!row) return;
    if (!okAmt) return setError("금액을 숫자로 입력하세요");
    if (Number.isNaN(ua)) return setError("초과수당 금액을 숫자로 입력하세요");
    if (hourly) {
      if (!(span > 0)) return setError("지정 퇴근은 지정 출근보다 늦어야 합니다");
      if (brkMin < 0 || brkMin >= span) return setError("휴게시간을 확인하세요");
      if ((um > 0) !== (ua > 0)) return setError("초과수당 단위(분)와 금액은 둘 다 입력하거나 둘 다 비워 두세요");
    }
    const id = row.id;
    run(id, "rate", `계약 조건 추가됨 (${from}부터)`, async () => {
      const res = await api.addWorkerRate(id, {
        effective_from: from, pay_type: payType, amount: amt, vat_applied: vat, memo: rateMemo.trim() || null,
        ...(hourly ? { work_start: wStart, work_end: wEnd, break_min: brkMin, break_paid: brkPaid,
          ot_unit_min: um, ot_unit_amount: ua } : {}),
      });
      setNewRateId(res.id ?? null);
      setAmount("");
      setRateMemo("");
    });
  }
  const delRate = (rid: number) => {
    if (!row || !window.confirm("이 계약 조건 이력을 삭제할까요?")) return;
    run(row.id, "rate", "계약 이력 삭제됨", () => api.deleteWorkerRate(rid));
  };

  // 계정 선택: 운영 활성 우선, 현재 다른 사람이 쓰는 계정 표시 (최종 판단은 서버가 시작일 기준으로)
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

  const assign = () => {
    if (!row) return;
    const id = row.id;
    run(id, "account", `고정 계정 저장됨 (${accFrom}부터)`, async () => {
      const res = await api.assignWorkerAccount(id, { manager_id: mgr ? Number(mgr) : null, start_date: accFrom });
      setNewAccId(res.id ?? null);
    });
  };
  const delAcc = (aid: number) => {
    if (!row || !window.confirm("이 계정 이력을 삭제할까요?")) return;
    run(row.id, "account", "계정 이력 삭제됨", () => api.deleteWorkerAccount(aid));
  };

  function close() {
    if ((basicDirty && !isNew ? true : isNew && basicDirty) || rateDirty) {
      if (!window.confirm("저장하지 않은 변경사항이 있습니다. 닫을까요?")) return;
    }
    onClose();
  }
  const label = (s: Sec, idle: string) => (busy === s ? "저장 중…" : idle);

  return (
    <Modal
      open
      size="lg"
      onClose={close}
      title={isNew ? "인력 추가" : <>{row.name} <span className="muted small">{INCOME_LABEL[row.income_type]}</span></>}
      footer={<Button onClick={close}>닫기</Button>}
    >
      {error && <div className="stack"><ErrorBox message={error} /></div>}

      <h3 className="sub-title">기본</h3>
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
            <input className="input" value={name} maxLength={50} onChange={(e) => setName(e.target.value)} placeholder="예: 김도연" />
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
          <label className="field field-wide">메모
            <input className="input" value={memo} maxLength={500} onChange={(e) => setMemo(e.target.value)} />
          </label>
          <div className="form-actions">
            {!isNew && income !== row.income_type && (
              <Chip tone="caution">구분 변경: 기존 계약 이력은 그대로, 새 계약부터 {INCOME_PAY[income] === "monthly" ? "월급제" : "시급제"}</Chip>
            )}
            {!isNew && basicDirty && <Chip tone="caution">변경됨 · 저장 전</Chip>}
            <SaveNote note={note} sec="basic" hide={!isNew && basicDirty} />
            <Button variant="primary" disabled={busy !== null || !basicDirty} onClick={saveBasic}>
              {label("basic", isNew ? "등록" : basicDirty ? "저장" : "저장됨")}
            </Button>
          </div>
        </div>
      ) : row && (
        <div className="muted small">{INCOME_LABEL[row.income_type]} · {row.active ? "활성" : "비활성"} · {row.memo || "메모 없음"}</div>
      )}
      {isNew && <p className="muted small">등록 후 계약 조건과 고정 계정을 입력할 수 있습니다.</p>}

      {row && (
        <>
          <h3 className="sub-title">계약 조건 이력 <span className="muted small">적용 시작일부터 다음 변경 전까지 적용</span></h3>
          {!detail ? <Spinner /> : detail.rates.length === 0 ? (
            <div className="muted small">입력된 계약 조건이 없습니다.</div>
          ) : (
            <DataTable columns={["적용 시작일", "급여", "지정 근무", "초과수당", "부가세",
              { label: "계약 일 기본급", num: true }, "메모", "입력자", ...(isAdmin ? ["관리"] : [])]}>
              {detail.rates.map((r) => (
                <tr key={r.id} className={r.id === newRateId ? "row-new" : undefined}>
                  <td>{r.effective_from}</td>
                  <td>{rateText(r)}</td>
                  <td>{workText(r)}</td>
                  <td>{r.pay_type === "hourly" ? otText(r) : "-"}</td>
                  <td>{r.vat_applied ? "포함" : "-"}</td>
                  <td className="num">{r.daily_base != null ? won(r.daily_base) : "-"}</td>
                  <td>{r.memo ?? ""}</td>
                  <td className="muted small">{r.created_by ?? "-"}</td>
                  {isAdmin && <td><Button size="sm" variant="danger" disabled={busy !== null} onClick={() => delRate(r.id)}>삭제</Button></td>}
                </tr>
              ))}
            </DataTable>
          )}

          {isAdmin && (
            <div className="form-grid mt">
              <label className="field">{hourly ? "시급(원)" : "월급(원)"}
                <input className="input" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)}
                  placeholder={hourly ? "예: 16,000" : "예: 3,000,000"} />
              </label>
              <label className="field">적용 시작일
                <input type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} />
              </label>
              <label className="field">부가세
                <select className="input" value={vat ? "1" : "0"} onChange={(e) => setVat(e.target.value === "1")}>
                  <option value="0">미적용</option>
                  <option value="1">10% 가산</option>
                </select>
              </label>
              {hourly && (
                <>
                  <label className="field">지정 출근
                    <input type="time" className="input" value={wStart} onChange={(e) => setWStart(e.target.value)} />
                  </label>
                  <label className="field">지정 퇴근
                    <input type="time" className="input" value={wEnd} onChange={(e) => setWEnd(e.target.value)} />
                  </label>
                  <label className="field">휴게(분)
                    <input className="input" inputMode="numeric" value={brk} onChange={(e) => setBrk(e.target.value)} />
                  </label>
                  <label className="field">휴게 처리
                    <select className="input" value={brkPaid ? "1" : "0"} onChange={(e) => setBrkPaid(e.target.value === "1")}>
                      <option value="1">유급 (근무시간에 포함)</option>
                      <option value="0">무급 (근무시간에서 차감)</option>
                    </select>
                  </label>
                  <label className="field">초과수당 단위(분)
                    <input className="input" inputMode="numeric" value={otMin} onChange={(e) => setOtMin(e.target.value)} placeholder="예: 30 (비우면 없음)" />
                  </label>
                  <label className="field">단위당 금액(원)
                    <input className="input" inputMode="numeric" value={otAmt} onChange={(e) => setOtAmt(e.target.value)} placeholder="예: 5,000" />
                  </label>
                </>
              )}
              <label className="field field-wide">메모
                <input className="input" value={rateMemo} maxLength={200} onChange={(e) => setRateMemo(e.target.value)} />
              </label>
              <div className="form-actions">
                {hourly && paidMin > 0 && okAmt && (
                  <span className="muted small">
                    계약 {hm(paidMin)} × {won(amt)} = 일 기본급 {won(dailyBase)}
                    {" · "}지정 시간 밖 1시간 근무 시 {won(hourOt)}
                    {um > 0 && ua > 0 ? ` (시급 ${won(amt)} + 초과수당 ${won(hourOt - Math.round(amt))})` : " (초과수당 없음)"}
                  </span>
                )}
                {!hourly && okAmt && <span className="muted small">월 {won(amt)} + 인센티브(월 입력)</span>}
                <SaveNote note={note} sec="rate" />
                <Button variant="primary" disabled={busy !== null} onClick={addRate}>{label("rate", "계약 추가")}</Button>
              </div>
            </div>
          )}
          <p className="muted small">
            기본급 = 시급 × 월 전체 유급 시간(초과 포함, 엑셀 월급여와 동일). 초과수당 = 날짜별 지정 시간 밖 근무를 단위(분)마다 지정 금액, 단위 미만 버림.
            출근은 지문이 지정 시각보다 빨라도 지정 시각으로 인정합니다.
          </p>

          <h3 className="sub-title">고정 계정 이력 <span className="muted small">하루만 바뀌는 경우는 근무 입력에서 일 단위 예외로 처리</span></h3>
          {!detail ? <Spinner /> : detail.accounts.length === 0 ? (
            <div className="muted small">배정된 계정이 없습니다.</div>
          ) : (
            <DataTable columns={["시작일", "계정", "입력자", ...(isAdmin ? ["관리"] : [])]}>
              {detail.accounts.map((a) => (
                <tr key={a.id} className={a.id === newAccId ? "row-new" : undefined}>
                  <td>{a.start_date}</td>
                  <td>{a.manager_id != null
                    ? <><span className="dot" style={{ background: a.manager_color ?? "#9ca3af" }} /> {a.manager_name ?? `#${a.manager_id}`}</>
                    : "계정 없음"}</td>
                  <td className="muted small">{a.created_by ?? "-"}</td>
                  {isAdmin && <td><Button size="sm" variant="danger" disabled={busy !== null} onClick={() => delAcc(a.id)}>삭제</Button></td>}
                </tr>
              ))}
            </DataTable>
          )}
          {isAdmin && (
            <div className="form-grid mt">
              <label className="field field-wide">계정
                <select className="input" value={mgr} onChange={(e) => setMgr(e.target.value)}>
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
                <input type="date" className="input" value={accFrom} onChange={(e) => setAccFrom(e.target.value)} />
              </label>
              <div className="form-actions">
                <SaveNote note={note} sec="account" />
                <Button variant="primary" disabled={busy !== null} onClick={assign}>{label("account", "계정 저장")}</Button>
              </div>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
