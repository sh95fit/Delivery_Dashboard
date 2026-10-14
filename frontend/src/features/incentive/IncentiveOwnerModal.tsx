import { useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import ErrorBox from "@/components/ui/ErrorBox";
import { saveIncOwner } from "@/api/incentive";
import type { IncDayRow, IncDayView } from "@/api/incentive";
import { errText } from "@/lib/form";

type Props = { row: IncDayRow; view: IncDayView; onClose: () => void; onSaved: () => void };

export default function IncentiveOwnerModal({ row, view, onClose, onSaved }: Props) {
  const o = row.owner;
  const chosen = o.source === "chosen";
  const [wid, setWid] = useState(chosen && o.worker_id != null ? String(o.worker_id) : "");
  const [memo, setMemo] = useState(chosen ? o.memo ?? "" : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(clear: boolean) {
    if (!clear && !wid) { setError("담당자를 고르세요"); return; }
    setBusy(true);
    try {
      await saveIncOwner(view.date, { manager_id: row.manager_id, worker_id: clear ? null : Number(wid),
        memo: clear ? null : memo.trim() || null });
      onSaved();
      onClose();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open title={`${view.date} ${row.manager_name} 담당자`} onClose={onClose}
      footer={<>
        {chosen && <Button onClick={() => save(true)} disabled={busy}>지정 해제 (기본 규칙으로)</Button>}
        <Button onClick={onClose} disabled={busy}>취소</Button>
        <Button variant="primary" onClick={() => save(false)} disabled={busy}>{busy ? "저장 중…" : "지정"}</Button>
      </>}>
      {error && <ErrorBox message={error} />}
      <div className="muted small">
        지금: {o.worker_id != null ? `${o.name} (${o.source === "chosen" ? "담당 지정" : o.source === "log" ? "근무 기록 그날 계정" : "고정 계정"})` : `미확인 — ${o.why ?? ""}`}
        <br />고정 담당자가 부상·휴가로 빠지고 다른 사람이 뛴 날에 지정하세요 (정규직 포함). 지정이 근무 기록·고정 계정보다 우선합니다.
      </div>
      <label className="mt">담당자
        <select className="input" value={wid} onChange={(e) => setWid(e.target.value)}>
          <option value="">선택</option>
          {view.workers.map((w) => (
            <option key={w.worker_id} value={w.worker_id}>
              {w.name} · {w.pay_type === "monthly" ? "정규직" : "시급"}{w.fixed_name ? ` · 고정 ${w.fixed_name}` : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="mt">메모
        <input className="input" maxLength={200} value={memo} placeholder="예: 홍길동 부상 대체"
          onChange={(e) => setMemo(e.target.value)} />
      </label>
    </Modal>
  );
}
