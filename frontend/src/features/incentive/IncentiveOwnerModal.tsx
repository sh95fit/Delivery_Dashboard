import { useState } from "react";
import type { CSSProperties } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import ErrorBox from "@/components/ui/ErrorBox";
import { saveIncOwner } from "@/api/incentive";
import type { IncDayRow, IncDayView } from "@/api/incentive";
import { errText } from "@/lib/form";

type Props = { row: IncDayRow; view: IncDayView; onClose: () => void; onSaved: () => void };
type Mode = "add" | "replace";

// [S2-P4c-2a] 담당 지정 방식
const MODES: { v: Mode; title: string; desc: string }[] = [
  { v: "add", title: "추가 담당", desc: "본인 노선도 하고 이 계정까지 처리 · 본인 고정 계정 담당 유지 · 인건비는 본인 계정" },
  { v: "replace", title: "대체 담당", desc: "본인 계정 대신 이 계정만 처리 · 그날 본인 고정 계정은 담당 없음" },
];

const S: Record<string, CSSProperties> = {
  section: { marginTop: 14 },
  label: { display: "block", fontWeight: 600, marginBottom: 6 },
  modes: { display: "grid", gap: 8 },
  card: { display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 12px",
          border: "1px solid #d0d5dd", borderRadius: 8, cursor: "pointer" },
  cardOn: { borderColor: "#2563eb", background: "#eff6ff" },
  radio: { marginTop: 3 },
  title: { fontWeight: 600 },
  full: { width: "100%", boxSizing: "border-box" },
  warn: { marginTop: 6, color: "#b54708" },
};

const SOURCE: Record<string, string> = { chosen: "담당 지정", log: "근무 기록 그날 계정", fixed: "고정 계정" };

export default function IncentiveOwnerModal({ row, view, onClose, onSaved }: Props) {
  const o = row.owner;
  const chosen = o.source === "chosen";
  const [wid, setWid] = useState(chosen && o.worker_id != null ? String(o.worker_id) : "");
  const [memo, setMemo] = useState(chosen ? o.memo ?? "" : "");
  const [mode, setMode] = useState<Mode>(chosen ? (o.mode ?? "replace") : "add");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const picked = view.workers.find((w) => String(w.worker_id) === wid);

  async function save(clear: boolean) {
    if (!clear && !wid) { setError("담당자를 고르세요"); return; }
    setBusy(true);
    try {
      await saveIncOwner(view.date, { manager_id: row.manager_id, worker_id: clear ? null : Number(wid),
        memo: clear ? null : memo.trim() || null, mode });
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
        지금: {o.worker_id != null
          ? `${o.name} (${SOURCE[o.source ?? ""] ?? "-"}${chosen ? ` · ${o.mode === "add" ? "추가" : "대체"} 담당` : ""})`
          : `미확인 — ${o.why ?? ""}`}
        <br />다른 사람이 이 계정 노선을 뛴 날에 지정하세요 (정규직 포함). 지정이 근무 기록·고정 계정보다 우선합니다.
      </div>

      <div style={S.section}>
        <span style={S.label}>지정 방식</span>
        <div style={S.modes}>
          {MODES.map((m) => (
            <label key={m.v} style={{ ...S.card, ...(mode === m.v ? S.cardOn : {}) }}>
              <input type="radio" name="owner-mode" style={S.radio}
                checked={mode === m.v} onChange={() => setMode(m.v)} />
              <span>
                <span style={S.title}>{m.title}</span>
                <br /><span className="muted small">{m.desc}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      <div style={S.section}>
        <span style={S.label}>담당자</span>
        <select className="input" style={S.full} value={wid} onChange={(e) => setWid(e.target.value)}>
          <option value="">선택</option>
          {view.workers.map((w) => (
            <option key={w.worker_id} value={w.worker_id}>
              {w.name} · {w.pay_type === "monthly" ? "정규직" : "시급"}{w.fixed_name ? ` · 고정 ${w.fixed_name}` : ""}
            </option>
          ))}
        </select>
        {mode === "replace" && picked?.fixed_name && picked.fixed_name !== row.manager_name && (
          <div className="small" style={S.warn}>
            대체 담당이라 그날 {picked.name}의 고정 계정 '{picked.fixed_name}'은 담당 없음이 됩니다 — 그 노선도 뛰었다면 추가 담당을 고르세요
          </div>
        )}
      </div>

      <div style={S.section}>
        <span style={S.label}>메모</span>
        <input className="input" style={S.full} maxLength={200} value={memo}
          placeholder="예: 홍길동 병가 대신 배송" onChange={(e) => setMemo(e.target.value)} />
      </div>
    </Modal>
  );
}
