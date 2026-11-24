import { useEffect, useState } from "react";
import Modal from "@/components/ui/Modal";
import { type UserRow, type PermSetLite, setUserPermSet, setUserActive } from "@/api/users";

type Props = { user: UserRow | null; sets: PermSetLite[]; onClose: () => void; onSaved: () => void };

export default function UserEditModal({ user, sets, onClose, onSaved }: Props) {
  const [psId, setPsId] = useState<number | "">("");
  const [active, setActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (user) { setPsId(user.permission_set_id ?? ""); setActive(user.status === "active"); setErr(""); }
  }, [user]);
  if (!user) return null;

  const psChanged = !user.is_super && psId !== "" && psId !== user.permission_set_id;
  const activeChanged = active !== (user.status === "active");
  const dirty = psChanged || activeChanged;

  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (psChanged) await setUserPermSet(user.email, psId as number);
      if (activeChanged) await setUserActive(user.email, active);
      onSaved(); onClose();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <Modal open title={user.email} onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose} disabled={busy}>닫기</button>
        <button className="btn btn-primary" onClick={save} disabled={!dirty || busy}>{busy ? "저장 중…" : "저장"}</button>
      </>}>
      <div className="stack">
        {err && <p className="error-box">{err}</p>}
        <label className="stack">
          <span className="small muted">권한셋</span>
          {user.is_super ? <span>전체 (마스터)</span> : (
            <select className="input" value={psId} onChange={(e) => setPsId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">선택</option>
              {sets.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
        </label>
        <label className="stack">
          <span className="small muted">대시보드 상태</span>
          <select className="input" value={active ? "1" : "0"} disabled={!user.can_deactivate && active}
            onChange={(e) => setActive(e.target.value === "1")}>
            <option value="1">활성</option>
            <option value="0">비활성</option>
          </select>
          {!user.can_deactivate && <span className="small muted">마스터와 본인 계정은 비활성화할 수 없습니다.</span>}
        </label>
        <div className="stack">
          <span className="small muted">메모 (읽기 전용 · 수정 기능은 다음 단계)</span>
          <span>{user.memo || "-"}</span>
        </div>
      </div>
    </Modal>
  );
}
