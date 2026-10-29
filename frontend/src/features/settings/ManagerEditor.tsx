import { useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import SaveNote, { nowHms } from "@/components/ui/SaveNote";
import type { SaveNoteState } from "@/components/ui/SaveNote";
import { OPS_LABEL, saveManagerProfile } from "@/api/masters";
import type { ManagerRow } from "@/api/masters";
import { errText } from "@/lib/form";
import { kstDateTime } from "@/lib/format";

/* [S3-P2h-3a] 계정 = 운영 배송 기록 단위. 대시보드 상태·메모만 저장 (급여는 인력 계약 조건, 차량은 인력 차량 이용) */

type Props = { row: ManagerRow; isAdmin: boolean; onChanged: () => Promise<void>; onClose: () => void };

export default function ManagerEditor({ row, isAdmin, onChanged, onClose }: Props) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<SaveNoteState<"profile"> | null>(null);
  const [active, setActive] = useState(row.active);
  const [memo, setMemo] = useState(row.memo ?? "");
  const dirty = active !== row.active || memo.trim() !== (row.memo ?? "").trim();
  const opsOn = row.ops_status === "active";

  /** 저장 → 목록 다시 읽기 → 결과 표시. 저장 실패와 새로고침 실패를 구분한다 */
  async function save() {
    setBusy(true);
    setError("");
    setNote(null);
    try {
      await saveManagerProfile(row.manager_id, { active, memo: memo.trim() || null });
    } catch (e) {
      setError(errText(e));
      setNote({ sec: "profile", ok: false, text: "저장 실패", at: nowHms() });
      setBusy(false);
      return;
    }
    try {
      await onChanged();
      setNote({ sec: "profile", ok: true, text: "저장됨", at: nowHms() });
    } catch {
      setNote({ sec: "profile", ok: true, text: "저장됨 (화면 새로고침 실패 — F5로 확인)", at: nowHms() });
    } finally {
      setBusy(false);
    }
  }

  function close() {
    if (dirty && !window.confirm("저장하지 않은 변경사항이 있습니다. 닫을까요?")) return;
    onClose();
  }

  return (
    <Modal
      open
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
            {dirty && <Chip tone="caution">변경됨 · 저장 전</Chip>}
            <SaveNote note={note} sec="profile" hide={dirty} />
            <Button variant="primary" disabled={busy || !dirty} onClick={save}>
              {busy ? "저장 중…" : dirty ? "저장" : "저장됨"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="muted small mt">대시보드 {row.active ? "활성" : "비활성"} · {row.memo || "메모 없음"}</div>
      )}
      <p className="muted small">
        {row.updated_at ? <>마지막 저장 {kstDateTime(row.updated_at)} · {row.updated_by ?? "-"}. </> : <>대시보드에서 저장한 적 없음(운영 상태를 따름). </>}
        과거 배송·비용 기록은 그대로 유지됩니다.
      </p>

      <h3 className="sub-title">연결 <span className="muted small">오늘 기준</span></h3>
      <div className="kv-line">
        <span className="muted small">고정 사용 인력</span>
        <span>{row.workers.length ? row.workers.join(", ") : <span className="muted">없음</span>}</span>
      </div>
      <p className="muted small">
        계정은 운영 배송 기록(배송지·완료 시각·매출)의 단위입니다. 연결은 인력 화면 &gt; 고정 계정에서 하고,
        하루만 다른 사람이 쓰면 근무 기록의 그날 계정이나 인센티브 담당 지정으로 처리합니다.
        급여·계약 조건은 인력에서, 차량은 그날 담당 인력의 차량 이용 이력으로 정해집니다 (계정에는 급여·차량을 넣지 않습니다).
      </p>
    </Modal>
  );
}
