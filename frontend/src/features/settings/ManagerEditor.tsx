import { useEffect, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import * as api from "@/api/masters";
import { OPS_LABEL, PAY_LABEL, payText, scheduleText } from "@/api/masters";
import type { ManagerDetail, ManagerRow, PayType, Vehicle } from "@/api/masters";
import { errText, parseAmount } from "@/lib/form";
import { hm, todayKst, won } from "@/lib/format";

type Props = {
  row: ManagerRow;
  vehicles: Vehicle[];
  isAdmin: boolean;
  onChanged: () => Promise<void>;
  onClose: () => void;
};
type Sec = "profile" | "rate" | "vehicle";
type Note = { sec: Sec; ok: boolean; text: string; at: string };

export const nowHms = () =>
  new Date().toLocaleTimeString("ko-KR", { hour12: false, timeZone: "Asia/Seoul" });
const kstDateTime = (s: string | null) => {
  if (!s) return "";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s
    : d.toLocaleString("ko-KR", { hour12: false, timeZone: "Asia/Seoul",
        year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};

const toMin = (s: string) => {
  const m = /^(\d{1,2}):(\d{2})/.exec(s);
  return m ? Number(m[1]) * 60 + Number(m[2]) : NaN;
};
/** 근로기준법 54조: 근로 4시간 이상 30분, 8시간 이상 1시간 (참고 경고) */
const legalBreak = (workMin: number) => (workMin >= 480 ? 60 : workMin >= 240 ? 30 : 0);

function SaveNote({ note, sec, hide }: { note: Note | null; sec: Sec; hide?: boolean }) {
  if (!note || note.sec !== sec || hide) return null;
  return (
    <span className={`save-note ${note.ok ? "ok" : "fail"}`} role="status" aria-live="polite">
      {note.ok ? "✓" : "✕"} {note.text} · {note.at}
    </span>
  );
}

export default function ManagerEditor({ row, vehicles, isAdmin, onChanged, onClose }: Props) {
  const cur = row.pay;
  const [detail, setDetail] = useState<ManagerDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<Sec | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  const [newRateId, setNewRateId] = useState<number | null>(null);
  const [newAssignId, setNewAssignId] = useState<number | null>(null);
  const [active, setActive] = useState(row.active);
  const [memo, setMemo] = useState(row.memo ?? "");
  const [payType, setPayType] = useState<PayType>(cur?.pay_type ?? "hourly");
  const [amount, setAmount] = useState("");
  const [payFrom, setPayFrom] = useState(todayKst());
  const [payMemo, setPayMemo] = useState("");
  const [wStart, setWStart] = useState(cur?.work_start ?? "09:00");
  const [wEnd, setWEnd] = useState(cur?.work_end ?? "15:00");
  const [brk, setBrk] = useState(String(cur?.break_min ?? 30));
  const [brkPaid, setBrkPaid] = useState(cur?.break_paid ?? false);
  const [vehicleId, setVehicleId] = useState(row.vehicle ? String(row.vehicle.vehicle_id) : "");
  const [vFrom, setVFrom] = useState(todayKst());

  const load = async () => setDetail(await api.getManager(row.manager_id));

  useEffect(() => {
    load().catch((e) => setError(errText(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row.manager_id]);

  /** 저장 → 서버 값 다시 읽기 → 결과 표시. 저장 실패와 새로고침 실패를 구분한다 */
  async function run(sec: Sec, okText: string, fn: () => Promise<unknown>) {
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
      await Promise.all([load(), onChanged()]);
      setNote({ sec, ok: true, text: okText, at: nowHms() });
    } catch {
      setNote({ sec, ok: true, text: `${okText} (화면 새로고침 실패 — F5로 확인)`, at: nowHms() });
    } finally {
      setBusy(null);
    }
  }

  // 기본 정보: 서버에서 다시 받은 row와 비교 → 같으면 실제 저장된 상태
  const profileDirty = active !== row.active || memo.trim() !== (row.memo ?? "").trim();
  const rateDirty = amount.trim() !== "" || payMemo.trim() !== "";
  const opsOn = row.ops_status === "active";

  function close() {
    if ((profileDirty || rateDirty) && !window.confirm("저장하지 않은 변경사항이 있습니다. 닫을까요?")) return;
    onClose();
  }

  // 시급 미리보기
  const amt = parseAmount(amount);
  const span = toMin(wEnd) - toMin(wStart);
  const brkMin = Number(brk) || 0;
  const paidMin = span > 0 ? (brkPaid ? span : Math.max(0, span - brkMin)) : 0;
  const workMin = span - brkMin;
  const needBreak = legalBreak(workMin);
  const daily = !Number.isNaN(amt) && amt > 0 ? Math.round((amt * paidMin) / 60) : 0;

  const saveProfile = () =>
    run("profile", "저장됨", () => api.saveManagerProfile(row.manager_id, { active, memo: memo.trim() || null }));

  function addRate() {
    const a = payType === "none" ? 0 : parseAmount(amount);
    if (Number.isNaN(a) || (payType !== "none" && a <= 0)) return setError("금액을 숫자로 입력하세요");
    if (payType === "hourly") {
      if (!(span > 0)) return setError("종료 시각은 시작 시각보다 늦어야 합니다");
      if (brkMin < 0 || brkMin >= span) return setError("휴게시간을 확인하세요");
    }
    run("rate", `급여 추가됨 (${payFrom}부터)`, async () => {
      const res = await api.addPayRate(row.manager_id, {
        pay_type: payType, amount: a, effective_from: payFrom, memo: payMemo.trim() || null,
        ...(payType === "hourly" ? { work_start: wStart, work_end: wEnd, break_min: brkMin, break_paid: brkPaid } : {}),
      });
      setNewRateId(res.id ?? null);
      setAmount("");
      setPayMemo("");
    });
  }

  const delRate = (id: number) => {
    if (window.confirm("이 급여 이력을 삭제할까요?")) run("rate", "급여 이력 삭제됨", () => api.deletePayRate(id));
  };
  const assign = () =>
    run("vehicle", `차량 배정 저장됨 (${vFrom}부터)`, async () => {
      const res = await api.assignVehicle(row.manager_id, { vehicle_id: vehicleId ? Number(vehicleId) : null, start_date: vFrom });
      setNewAssignId(res.id ?? null);
    });
  const delAssign = (id: number) => {
    if (window.confirm("이 차량 배정 이력을 삭제할까요?")) run("vehicle", "배정 이력 삭제됨", () => api.deleteAssignment(id));
  };

  const selectable = vehicles.filter((v) => v.active || String(v.id) === vehicleId);
  const label = (s: Sec, idle: string) => (busy === s ? "저장 중…" : idle);

  return (
    <Modal
      open
      size="lg"
      onClose={close}
      title={<><span className="dot" style={{ background: row.color ?? "#9ca3af" }} />{row.name ?? `#${row.manager_id}`}</>}
      footer={<Button onClick={close}>닫기</Button>}
    >
      {error && <div className="stack"><ErrorBox message={error} /></div>}

      <h3 className="sub-title">기본</h3>
      <div className="kv-line">
        <span className="muted small">운영 계정 상태</span>
        <span title={`운영 DB status: ${row.ops_status_raw ?? "(없음)"}`}>
          {opsOn ? <Chip tone="ok">{OPS_LABEL[row.ops_status]}</Chip>
            : <Chip tone={row.ops_status === "unknown" ? "caution" : undefined}>{OPS_LABEL[row.ops_status]}</Chip>}
        </span>
        <span className="muted small">운영 DB 값 · 여기서 변경 불가</span>
      </div>
      {!opsOn && row.active && (
        <div className="mt"><Chip tone="caution">운영 DB에서 비활성 계정입니다. 대시보드 상태도 비활성으로 바꾸는 것을 권장합니다</Chip></div>
      )}

      {isAdmin ? (
        <div className="form-grid mt">
          <label className="field">대시보드 상태
            <select className="input" value={active ? "1" : "0"} onChange={(e) => setActive(e.target.value === "1")}>
              <option value="1">활성</option>
              <option value="0">비활성</option>
            </select>
          </label>
          <label className="field field-wide">메모
            <input className="input" value={memo} maxLength={500} onChange={(e) => setMemo(e.target.value)} />
          </label>
          <div className="form-actions">
            {profileDirty && <Chip tone="caution">변경됨 · 저장 전</Chip>}
            <SaveNote note={note} sec="profile" hide={profileDirty} />
            <Button variant="primary" disabled={busy !== null || !profileDirty} onClick={saveProfile}>
              {label("profile", profileDirty ? "저장" : "저장됨")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="muted small mt">대시보드 {row.active ? "활성" : "비활성"} · {row.memo || "메모 없음"}</div>
      )}
      <p className="muted small">
        {row.updated_at ? <>마지막 저장 {kstDateTime(row.updated_at)} · {row.updated_by ?? "-"}. </> : <>대시보드에서 저장한 적 없음(운영 상태를 따름). </>}
        비활성 매니저는 급여 미입력 집계에서 빠집니다. 과거 배송·비용 기록은 그대로 유지됩니다.
      </p>

      <h3 className="sub-title">급여·근무 기준 이력 <span className="muted small">적용 시작일부터 다음 변경 전까지 적용</span></h3>
      {!detail ? (
        <Spinner />
      ) : detail.rates.length === 0 ? (
        <div className="muted small">입력된 급여가 없습니다.</div>
      ) : (
        <DataTable columns={["적용 시작일", "급여", "근무 기준", { label: "예상 일 인건비", num: true }, "메모", "입력자", ...(isAdmin ? ["관리"] : [])]}>
          {detail.rates.map((r) => (
            <tr key={r.id} className={r.id === newRateId ? "row-new" : undefined}>
              <td>{r.effective_from}</td>
              <td>{payText(r)}</td>
              <td>{scheduleText(r)}</td>
              <td className="num">{r.daily_cost != null ? won(r.daily_cost) : "-"}</td>
              <td>{r.memo ?? ""}</td>
              <td className="muted small">{r.created_by ?? "-"}</td>
              {isAdmin && (
                <td><Button size="sm" variant="danger" disabled={busy !== null} onClick={() => delRate(r.id)}>삭제</Button></td>
              )}
            </tr>
          ))}
        </DataTable>
      )}

      {isAdmin && (
        <div className="form-grid mt">
          <label className="field">유형
            <select className="input" value={payType} onChange={(e) => setPayType(e.target.value as PayType)}>
              {(Object.keys(PAY_LABEL) as PayType[]).map((k) => <option key={k} value={k}>{PAY_LABEL[k]}</option>)}
            </select>
          </label>
          <label className="field">{payType === "hourly" ? "시급(원)" : "월급(원)"}
            <input className="input" inputMode="numeric" value={payType === "none" ? "" : amount}
              disabled={payType === "none"} onChange={(e) => setAmount(e.target.value)}
              placeholder={payType === "hourly" ? "예: 12,000" : "예: 3,000,000"} />
          </label>
          <label className="field">적용 시작일
            <input type="date" className="input" value={payFrom} onChange={(e) => setPayFrom(e.target.value)} />
          </label>
          {payType === "hourly" && (
            <>
              <label className="field">근무 시작
                <input type="time" className="input" value={wStart} onChange={(e) => setWStart(e.target.value)} />
              </label>
              <label className="field">근무 종료
                <input type="time" className="input" value={wEnd} onChange={(e) => setWEnd(e.target.value)} />
              </label>
              <label className="field">휴게(분)
                <input className="input" inputMode="numeric" value={brk} onChange={(e) => setBrk(e.target.value)} />
              </label>
              <label className="field">휴게 처리
                <select className="input" value={brkPaid ? "1" : "0"} onChange={(e) => setBrkPaid(e.target.value === "1")}>
                  <option value="0">무급 (인건비 제외)</option>
                  <option value="1">유급 (인건비 포함)</option>
                </select>
              </label>
            </>
          )}
          <label className="field field-wide">메모
            <input className="input" value={payMemo} maxLength={200} onChange={(e) => setPayMemo(e.target.value)} />
          </label>
          <div className="form-actions">
            {payType === "hourly" && paidMin > 0 && (
              <span className="muted small">유급 {hm(paidMin)}{daily ? ` × ${won(amt)} = 일 ${won(daily)}` : ""}</span>
            )}
            {payType === "hourly" && span > 0 && brkMin < needBreak && (
              <Chip tone="caution">근로 {hm(workMin)} → 법정 휴게 {needBreak}분 이상</Chip>
            )}
            {payType === "monthly" && !Number.isNaN(amt) && amt > 0 && <span className="muted small">{won(amt)}</span>}
            <SaveNote note={note} sec="rate" />
            <Button variant="primary" disabled={busy !== null} onClick={addRate}>{label("rate", "급여 추가")}</Button>
          </div>
        </div>
      )}
      <p className="muted small">
        시급제 예상 일 인건비 = 시급 × (근무시간 − 무급 휴게). 실제 인건비는 근무일지(출퇴근 기록) 단계에서 실제 시간으로 다시 계산합니다.
        월급제는 근무일수 기준으로 일할합니다(근무 입력 단계).
      </p>

      <h3 className="sub-title">차량 배정 이력</h3>
      {!detail ? (
        <Spinner />
      ) : detail.assignments.length === 0 ? (
        <div className="muted small">배정 이력이 없습니다.</div>
      ) : (
        <DataTable columns={["시작일", "차량", "입력자", ...(isAdmin ? ["관리"] : [])]}>
          {detail.assignments.map((a) => (
            <tr key={a.id} className={a.id === newAssignId ? "row-new" : undefined}>
              <td>{a.start_date}</td>
              <td>{a.vehicle_id ? `${a.plate_no ?? `#${a.vehicle_id}`}${a.model ? ` · ${a.model}` : ""}` : "차량 없음"}</td>
              <td className="muted small">{a.created_by ?? "-"}</td>
              {isAdmin && (
                <td><Button size="sm" variant="danger" disabled={busy !== null} onClick={() => delAssign(a.id)}>삭제</Button></td>
              )}
            </tr>
          ))}
        </DataTable>
      )}
      {isAdmin && (
        <div className="form-grid mt">
          <label className="field">차량
            <select className="input" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
              <option value="">차량 없음</option>
              {selectable.map((v) => <option key={v.id} value={v.id}>{v.plate_no}{v.model ? ` · ${v.model}` : ""}</option>)}
            </select>
          </label>
          <label className="field">시작일
            <input type="date" className="input" value={vFrom} onChange={(e) => setVFrom(e.target.value)} />
          </label>
          <div className="form-actions">
            <SaveNote note={note} sec="vehicle" />
            <Button variant="primary" disabled={busy !== null} onClick={assign}>{label("vehicle", "배정 저장")}</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
