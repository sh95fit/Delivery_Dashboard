import { useEffect, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import * as api from "@/api/masters";
import { PAY_LABEL, payText, scheduleText } from "@/api/masters";
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

const toMin = (s: string) => {
  const m = /^(\d{1,2}):(\d{2})/.exec(s);
  return m ? Number(m[1]) * 60 + Number(m[2]) : NaN;
};
/** 근로기준법 54조: 근로 4시간 이상 30분, 8시간 이상 1시간 (참고 경고) */
const legalBreak = (workMin: number) => (workMin >= 480 ? 60 : workMin >= 240 ? 30 : 0);

export default function ManagerEditor({ row, vehicles, isAdmin, onChanged, onClose }: Props) {
  const cur = row.pay;
  const [detail, setDetail] = useState<ManagerDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
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

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load();
      await onChanged();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  // 시급 미리보기
  const amt = parseAmount(amount);
  const span = toMin(wEnd) - toMin(wStart);
  const brkMin = Number(brk) || 0;
  const paidMin = span > 0 ? (brkPaid ? span : Math.max(0, span - brkMin)) : 0;
  const workMin = span - brkMin;
  const needBreak = legalBreak(workMin);
  const daily = !Number.isNaN(amt) && amt > 0 ? Math.round((amt * paidMin) / 60) : 0;

  const saveProfile = () => run(() => api.saveManagerProfile(row.manager_id, { active, memo: memo.trim() || null }));

  function addRate() {
    const a = payType === "none" ? 0 : parseAmount(amount);
    if (Number.isNaN(a) || (payType !== "none" && a <= 0)) return setError("금액을 숫자로 입력하세요");
    if (payType === "hourly") {
      if (!(span > 0)) return setError("종료 시각은 시작 시각보다 늦어야 합니다");
      if (brkMin < 0 || brkMin >= span) return setError("휴게시간을 확인하세요");
    }
    run(async () => {
      await api.addPayRate(row.manager_id, {
        pay_type: payType, amount: a, effective_from: payFrom, memo: payMemo.trim() || null,
        ...(payType === "hourly" ? { work_start: wStart, work_end: wEnd, break_min: brkMin, break_paid: brkPaid } : {}),
      });
      setAmount("");
      setPayMemo("");
    });
  }

  const delRate = (id: number) => {
    if (window.confirm("이 급여 이력을 삭제할까요?")) run(() => api.deletePayRate(id));
  };
  const assign = () =>
    run(() => api.assignVehicle(row.manager_id, { vehicle_id: vehicleId ? Number(vehicleId) : null, start_date: vFrom }));
  const delAssign = (id: number) => {
    if (window.confirm("이 차량 배정 이력을 삭제할까요?")) run(() => api.deleteAssignment(id));
  };

  const selectable = vehicles.filter((v) => v.active || String(v.id) === vehicleId);

  return (
    <Modal
      open
      size="lg"
      onClose={onClose}
      title={<><span className="dot" style={{ background: row.color ?? "#9ca3af" }} />{row.name ?? `#${row.manager_id}`}</>}
      footer={<Button onClick={onClose}>닫기</Button>}
    >
      {error && <div className="stack"><ErrorBox message={error} /></div>}

      <h3 className="sub-title">기본</h3>
      {isAdmin ? (
        <div className="form-grid">
          <label className="field">상태
            <select className="input" value={active ? "1" : "0"} onChange={(e) => setActive(e.target.value === "1")}>
              <option value="1">활성</option>
              <option value="0">비활성</option>
            </select>
          </label>
          <label className="field field-wide">메모
            <input className="input" value={memo} maxLength={500} onChange={(e) => setMemo(e.target.value)} />
          </label>
          <div className="form-actions">
            <Button variant="primary" disabled={busy} onClick={saveProfile}>저장</Button>
          </div>
        </div>
      ) : (
        <div className="muted small">{row.active ? "활성" : "비활성"} · {row.memo || "메모 없음"}</div>
      )}
      <p className="muted small">비활성 매니저는 기본 목록과 급여 미입력 집계에서 빠집니다. 과거 배송·비용 기록은 그대로 유지됩니다.</p>

      <h3 className="sub-title">급여·근무 기준 이력 <span className="muted small">적용 시작일부터 다음 변경 전까지 적용</span></h3>
      {!detail ? (
        <Spinner />
      ) : detail.rates.length === 0 ? (
        <div className="muted small">입력된 급여가 없습니다.</div>
      ) : (
        <DataTable columns={["적용 시작일", "급여", "근무 기준", { label: "예상 일 인건비", num: true }, "메모", "입력자", ...(isAdmin ? ["관리"] : [])]}>
          {detail.rates.map((r) => (
            <tr key={r.id}>
              <td>{r.effective_from}</td>
              <td>{payText(r)}</td>
              <td>{scheduleText(r)}</td>
              <td className="num">{r.daily_cost != null ? won(r.daily_cost) : "-"}</td>
              <td>{r.memo ?? ""}</td>
              <td className="muted small">{r.created_by ?? "-"}</td>
              {isAdmin && (
                <td><Button size="sm" variant="danger" disabled={busy} onClick={() => delRate(r.id)}>삭제</Button></td>
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
            <Button variant="primary" disabled={busy} onClick={addRate}>급여 추가</Button>
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
            <tr key={a.id}>
              <td>{a.start_date}</td>
              <td>{a.vehicle_id ? `${a.plate_no ?? `#${a.vehicle_id}`}${a.model ? ` · ${a.model}` : ""}` : "차량 없음"}</td>
              <td className="muted small">{a.created_by ?? "-"}</td>
              {isAdmin && (
                <td><Button size="sm" variant="danger" disabled={busy} onClick={() => delAssign(a.id)}>삭제</Button></td>
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
            <Button variant="primary" disabled={busy} onClick={assign}>배정 저장</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
