import { useEffect, useState } from "react";
import Panel from "@/components/ui/Panel";
import Chip, { type ChipTone } from "@/components/ui/Chip";
import {
  type UserRow, type PermSetLite, type UserStatus, type InviteResult, listUsers, listPermSets, createUser,
  revokeUserInvite, resendInvite, deleteUser, clearInvite, statusLabel, fmtDate,
} from "@/api/users";
import UserEditModal from "./UserEditModal";

const TONE: Record<UserStatus, ChipTone> = {
  active: "ok", inactive: "danger", invited: "warn", expired: "caution", revoked: "neutral", none: "neutral",
};
type Filter = "active" | "inactive" | "all";

export default function UsersTab() {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [sets, setSets] = useState<PermSetLite[]>([]);
  const [email, setEmail] = useState("");
  const [psId, setPsId] = useState<number | "">("");
  const [days, setDays] = useState(7);
  const [memo, setMemo] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState<Filter>("active");
  const [editing, setEditing] = useState<UserRow | null>(null);

  const load = async () => {
    try {
      const [u, s] = await Promise.all([listUsers(), listPermSets()]);
      setRows(u); setSets(s); setErr("");
    } catch (e) { setErr((e as Error).message); }
  };
  useEffect(() => { load(); }, []);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr("");
    try { await fn(); await load(); return true; }
    catch (e) { setErr((e as Error).message); return false; }
    finally { setBusy(false); }
  };

  const [note, setNote] = useState("");
  useEffect(() => { if (!note) return; const t = setTimeout(() => setNote(""), 3000); return () => clearTimeout(t); }, [note]);
  const remove = (u: UserRow) => {
    if (!confirm(`${u.email} 계정을 완전히 삭제할까요? 목록과 권한에서 사라집니다.`)) return;
    run(() => deleteUser(u.email)).then((ok) => ok && setNote(`${u.email} 계정을 삭제했습니다`));
  };
  const mailNote = (to: string, r: InviteResult) =>
    r.mail_sent ? setNote(`${to} 주소로 초대 메일을 보냈습니다`)
      : setErr(`초대는 저장됐지만 메일을 보내지 못했습니다: ${r.mail_error ?? ""} (메일 다시 보내기를 눌러 주세요)`);

  const invite = async () => {
    const to = email.trim();
    setNote("");
    if (!to) return setErr("이메일을 입력하세요");
    if (psId === "") return setErr("권한셋을 선택하세요");
    if (days < 1 || days > 30) return setErr("유효기간은 1~30일입니다");
    const h: { r?: InviteResult } = {};
    const ok = await run(async () => { h.r = await createUser({ email: to, permission_set_id: psId, days, memo: memo.trim() || null }); });
    if (ok && h.r) { mailNote(to, h.r); setEmail(""); setMemo(""); setDays(7); }
  };

  const reinvite = async (u: UserRow) => {
    setNote("");
    if (!u.permission_set_id) return setErr("권한셋 정보가 없어 재초대할 수 없습니다");
    const h: { r?: InviteResult } = {};
    const ok = await run(async () => { h.r = await createUser({ email: u.email, permission_set_id: u.permission_set_id!, days: 7, memo: u.memo }); });
    if (ok && h.r) mailNote(u.email, h.r);
  };

  const resend = async (u: UserRow) => {
    setBusy(true); setErr(""); setNote("");
    try { mailNote(u.email, await resendInvite(u.email, u.days_left ?? 7)); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  const invites = rows.filter((u) => !u.is_super && ["invited", "expired", "revoked", "none"].includes(u.status));
  const members = rows.filter((u) => u.status === "active" || u.status === "inactive");
  const cnt = (s: UserStatus) => members.filter((u) => u.status === s).length;
  const shown = filter === "all" ? members : members.filter((u) => u.status === filter);
  const fBtn = (k: Filter, label: string) => (
    <button className={`tab${filter === k ? " active" : ""}`} onClick={() => setFilter(k)}>{label}</button>
  );  

  return (
    <>
      {err && <p className="error-box mt">{err}</p>}  

      <Panel title="사용자 추가" desc="초대 메일이 자동으로 발송됩니다. 받은 사람이 구글 로그인하면 사용자 목록으로 옮겨집니다.">
        <div className="form-row">
          <input className="input grow" placeholder="이메일" value={email} onChange={(e) => setEmail(e.target.value)} />
          <select className="input" value={psId} onChange={(e) => setPsId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">권한셋 선택</option>
            {sets.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <input className="input input-num" type="number" min={1} max={30} value={days}
            onChange={(e) => setDays(Number(e.target.value))} />
          <span className="muted small">일 유효</span>
          <input className="input grow" placeholder="메모(선택)" value={memo} onChange={(e) => setMemo(e.target.value)} />
          <button className="btn btn-primary" disabled={busy} onClick={invite}>{busy ? "발송 중…" : "초대 메일 발송"}</button>
        </div>

        {invites.length > 0 && (
          <div className="tbl-wrap mt">
            <table className="tbl">
              <thead><tr><th>초대 이메일</th><th>권한셋</th><th>상태</th><th>만료</th><th>메모</th><th>관리</th></tr></thead>
              <tbody>
                {invites.map((u) => (
                  <tr key={u.email}>
                    <td>{u.email}</td>
                    <td>{u.permission_set_name ?? "-"}</td>
                    <td><Chip tone={TONE[u.status]}>{statusLabel(u)}</Chip></td>
                    <td className="small">{fmtDate(u.expires_at)}</td>
                    <td className="small muted">{u.memo ?? ""}</td>
                    <td>
                      <div className="toolbar">
                        {u.status === "invited" ? (<>
                          <button className="btn btn-sm" disabled={busy} onClick={() => resend(u)}>메일 다시 보내기</button>
                          <button className="btn btn-sm btn-danger" disabled={busy}
                            onClick={() => confirm("초대를 취소할까요?") && run(() => revokeUserInvite(u.email))}>초대취소</button>
                        </>) : (
                          <>
                            <button className="btn btn-sm" disabled={busy} onClick={() => reinvite(u)}>재초대(7일)</button>
                            <button className="btn btn-sm btn-danger" disabled={busy}
                              onClick={() => confirm(`${u.email}을(를) 초대 목록에서 삭제할까요?`) &&
                                run(() => clearInvite(u.email)).then((ok) => ok && setNote("초대 목록에서 삭제했습니다"))}>목록에서 삭제</button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title={`사용자 ${members.length}명`}
        right={<div className="tabs">{fBtn("active", `활성 ${cnt("active")}`)}{fBtn("inactive", `비활성 ${cnt("inactive")}`)}{fBtn("all", `전체 ${members.length}`)}</div>}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>이메일</th><th>권한셋</th><th>상태</th><th>최근 로그인</th><th>메모</th><th>관리</th></tr></thead>
            <tbody>
              {shown.map((u) => (
                <tr key={u.email}>
                  <td>
                    {u.email}
                    {u.is_super && <span className="tag-inline"><Chip tone="internal">마스터</Chip></span>}
                    {u.is_me && <span className="muted tag-inline">(나)</span>}
                  </td>
                  <td>{u.is_super ? <span className="muted">전체</span> : (u.permission_set_name ?? <Chip tone="caution">미지정</Chip>)}</td>
                  <td><Chip tone={TONE[u.status]}>{statusLabel(u)}</Chip></td>
                  <td className="small">{fmtDate(u.last_login_at)}</td>
                  <td className="small muted">{u.memo ?? "-"}</td>
                  <td>
                    <div className="toolbar">
                      <button className="btn btn-sm" onClick={() => setEditing(u)}>편집</button>
                      {u.status === "inactive" && u.can_deactivate && (
                        <button className="btn btn-sm btn-danger" disabled={busy} onClick={() => remove(u)}>삭제</button>)}
                    </div>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={6} className="muted">해당하는 사용자가 없습니다</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>

      {note && <div className="toast" role="status">{note}</div>}
      <UserEditModal user={editing} sets={sets} onClose={() => setEditing(null)} onSaved={load} />
    </>
  );
}
