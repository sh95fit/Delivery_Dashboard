import { useEffect, useState } from "react";
import {
  UserRow, PermSetLite, listUsers, listPermSets, createUser, setUserPermSet,
  setUserActive, revokeUserInvite, statusLabel, STATUS_COLORS, fmtDate,
} from "../../api/users";

export default function UsersTab() {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [sets, setSets] = useState<PermSetLite[]>([]);
  const [email, setEmail] = useState("");
  const [psId, setPsId] = useState<number | "">("");
  const [days, setDays] = useState(7);
  const [memo, setMemo] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [u, s] = await Promise.all([listUsers(), listPermSets()]);
      setRows(u);
      setSets(s);
    } catch (e) {
      alert((e as Error).message);
    }
  };
  useEffect(() => { load(); }, []);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); await load(); }
    catch (e) { alert((e as Error).message); }
    finally { setBusy(false); }
  };

  const invite = () => {
    if (!email.trim()) return alert("이메일을 입력하세요");
    if (psId === "") return alert("권한셋을 선택하세요");
    if (days < 1 || days > 30) return alert("유효기간은 1~30일입니다");
    run(async () => {
      await createUser({ email: email.trim(), permission_set_id: psId, days, memo: memo.trim() || null });
      setEmail(""); setMemo(""); setDays(7);
    });
  };

  const reinvite = (u: UserRow) => {
    if (!u.permission_set_id) return alert("먼저 권한셋을 선택하세요");
    run(() => createUser({ email: u.email, permission_set_id: u.permission_set_id!, days: 7, memo: u.memo }));
  };

  const cell = { padding: "6px 8px", borderBottom: "1px solid #eee" } as const;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <input placeholder="이메일" value={email} onChange={(e) => setEmail(e.target.value)} />
        <select value={psId} onChange={(e) => setPsId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">권한셋 선택</option>
          {sets.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <input type="number" min={1} max={30} value={days} style={{ width: 70 }}
          onChange={(e) => setDays(Number(e.target.value))} />일
        <input placeholder="메모" value={memo} onChange={(e) => setMemo(e.target.value)} />
        <button disabled={busy} onClick={invite}>초대</button>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>{["이메일", "권한셋", "상태", "최근 로그인", "메모", "동작"].map((h) =>
            <th key={h} style={{ ...cell, textAlign: "left" }}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.email}>
              <td style={cell}>
                {u.email}
                {u.is_super && <b style={{ marginLeft: 6, color: "#7c3aed" }}>마스터</b>}
                {u.is_me && <span style={{ marginLeft: 6, color: "#666" }}>(나)</span>}
              </td>
              <td style={cell}>
                {u.is_super ? "전체" : (
                  <select disabled={busy} value={u.permission_set_id ?? ""}
                    onChange={(e) => e.target.value &&
                      run(() => setUserPermSet(u.email, Number(e.target.value)))}>
                    <option value="">선택</option>
                    {sets.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                )}
              </td>
              <td style={{ ...cell, color: STATUS_COLORS[u.status] }}>{statusLabel(u)}</td>
              <td style={cell}>{fmtDate(u.last_login_at)}</td>
              <td style={cell}>{u.memo ?? ""}</td>
              <td style={cell}>
                {u.status === "active" && u.can_deactivate && (
                  <button disabled={busy} onClick={() =>
                    confirm(`${u.email} 비활성화할까요?`) && run(() => setUserActive(u.email, false))}>
                    비활성화</button>)}
                {u.status === "inactive" && (
                  <button disabled={busy} onClick={() => run(() => setUserActive(u.email, true))}>활성화</button>)}
                {u.status === "invited" && (
                  <button disabled={busy} onClick={() =>
                    confirm("초대를 취소할까요?") && run(() => revokeUserInvite(u.email))}>초대취소</button>)}
                {["expired", "revoked", "none"].includes(u.status) && !u.is_super && (
                  <button disabled={busy} onClick={() => reinvite(u)}>재초대(7일)</button>)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
