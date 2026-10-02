import { useEffect, useRef, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import * as api from "@/api/masters";
import { PAY_LABEL } from "@/api/masters";
import type { ManagerDetail, ManagerRow, PayType, Vehicle } from "@/api/masters";
import { errText, parseAmount } from "@/lib/form";
import { todayKst, won } from "@/lib/format";

type Props = {
  row: ManagerRow;
  vehicles: Vehicle[];
  isAdmin: boolean;
  onChanged: () => Promise<void>;
  onClose: () => void;
};

export default function ManagerEditor({ row, vehicles, isAdmin, onChanged, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [detail, setDetail] = useState<ManagerDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(row.active);
  const [memo, setMemo] = useState(row.memo ?? "");
  const [payType, setPayType] = useState<PayType>(row.pay?.pay_type ?? "monthly");
  const [amount, setAmount] = useState("");
  const [payFrom, setPayFrom] = useState(todayKst());
  const [payMemo, setPayMemo] = useState("");
  const [vehicleId, setVehicleId] = useState(row.vehicle ? String(row.vehicle.vehicle_id) : "");
  const [vFrom, setVFrom] = useState(todayKst());

  const load = async () => setDetail(await api.getManager(row.manager_id));

  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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

  const saveProfile = () => run(() => api.saveManagerProfile(row.manager_id, { active, memo: memo.trim() || null }));

  function addRate() {
    const a = payType === "none" ? 0 : parseAmount(amount);
    if (Number.isNaN(a) || (payType !== "none" && a <= 0)) {
      setError("금액을 숫자로 입력하세요");
      return;
    }
    run(async () => {
      await api.addPayRate(row.manager_id, { pay_type: payType, amount: a, effective_from: payFrom, memo: payMemo.trim() || null });
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

  const amt = parseAmount(amount);
  const selectable = vehicles.filter((v) => v.active || String(v.id) === vehicleId);

  return (
    <div ref={ref}>
      <Panel
        title={<><span className="dot" style={{ background: row.color ?? "#9ca3af" }} /> {row.name ?? `#${row.manager_id}`}</>}
        right={<Button size="sm" variant="ghost" onClick={onClose}>닫기</Button>}
      >
        {error && <div className="stack"><ErrorBox message={error} /></div>}

        <h3 className="sub-title">기본</h3>
        {isAdmin ? (
          <div className="form-grid">
            <label className="field">상태
              <select className="input" value={active ? "1" : "0"} onChange={(e) => setActive(e.target.value === "1")}>
                <option value="1">사용</option>
                <option value="0">중지</option>
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
          <div className="muted small">{row.active ? "사용" : "중지"} · {row.memo || "메모 없음"}</div>
        )}

        <h3 className="sub-title">급여 이력 <span className="muted small">적용 시작일부터 다음 변경 전까지 적용</span></h3>
        {!detail ? (
          <Spinner />
        ) : detail.rates.length === 0 ? (
          <div className="muted small">입력된 급여가 없습니다.</div>
        ) : (
          <DataTable columns={["적용 시작일", "유형", { label: "금액", num: true }, "메모", "입력자", ...(isAdmin ? ["관리"] : [])]}>
            {detail.rates.map((r) => (
              <tr key={r.id}>
                <td>{r.effective_from}</td>
                <td>{PAY_LABEL[r.pay_type]}</td>
                <td className="num">{r.pay_type === "none" ? "-" : won(r.amount)}</td>
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
            <label className="field">메모
              <input className="input" value={payMemo} maxLength={200} onChange={(e) => setPayMemo(e.target.value)} />
            </label>
            <div className="form-actions">
              {!Number.isNaN(amt) && amt > 0 && payType !== "none" && <span className="muted small">{won(amt)}</span>}
              <Button variant="primary" disabled={busy} onClick={addRate}>급여 추가</Button>
            </div>
          </div>
        )}
        <p className="muted small">
          월급은 실제 근무일수로 나눠 일 인건비로, 시급은 근무시간 × 시급으로 계산합니다(근무 입력 단계).
          시간 초과 추가 지급은 근무 입력에서 일자·금액으로 따로 기록합니다.
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
      </Panel>
    </div>
  );
}
