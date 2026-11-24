import { useEffect, useState, type CSSProperties } from "react";
import { ApiError } from "@/api/client";
import { listRules } from "@/api/permissions";
import {
  listAccounts, setAccountActive, listInvitations, createInvitation, revokeInvitation,
  STATE_LABELS, STATE_COLORS, fmtDate, type Account, type Invitation,
} from "@/api/accounts";

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));
const cell: CSSProperties = { border: "1px solid #ddd", padding: "6px 8px", textAlign: "left" };
const box: CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 };
const errStyle: CSSProperties = { color: "#c0392b", margin: "8px 0" };
const warnStyle: CSSProperties = { color: "#b45309", background: "#fff7ed", padding: "6px 10px", borderRadius: 6, margin: "8px 0" };

/** 입력 중 이메일에 맞는 '활성' 접근 규칙이 있는지 (백엔드 has_rule과 같은 기준) */
function matchesRule(email: string, rules: { kind: string; value: string; active: boolean }[]) {
  const e = email.trim().toLowerCase();
  if (!e.includes("@")) return true; // 형식 미완성일 땐 경고 안 띄움
  const domain = e.split("@")[1];
  return rules.some((r) => r.active && (
    (r.kind === "email" && r.value.toLowerCase() === e) ||
    (r.kind === "domain" && r.value.toLowerCase() === domain)));
}

export default function AccountsTab() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [rules, setRules] = useState<{ kind: string; value: string; active: boolean }[]>([]);
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [days, setDays] = useState(7);
  const [memo, setMemo] = useState("");

  const load = () =>
    Promise.all([listAccounts(), listInvitations(), listRules()])
      .then(([a, i, r]) => { setAccounts(a); setInvites(i); setRules(r); })
      .catch((e) => setErr(errMsg(e)));
  useEffect(() => { load(); }, []);

  const toggle = async (a: Account) => {
    const next = !a.active;
    if (!next && !window.confirm(`${a.email} 계정을 비활성화할까요? 즉시 로그인이 차단됩니다.`)) return;
    setErr(""); setNotice("");
    try { await setAccountActive(a.id, next); await load(); }
    catch (e) { setErr(errMsg(e)); } // 본인 계정은 서버가 거부하고 여기서 메시지를 보여줌
  };

  const noRule = email.trim() !== "" && !matchesRule(email, rules);

  const invite = async () => {
    if (days < 1 || days > 30) { setErr("유효기간은 1~30일입니다"); return; }
    if (noRule && !window.confirm("이 이메일에 맞는 접근 규칙이 없습니다.\n규칙이 없으면 로그인해도 가입되지 않습니다. 그래도 초대할까요?")) return;
    setBusy(true); setErr(""); setNotice("");
    try {
      const r = await createInvitation({ email: email.trim(), days, memo: memo.trim() || null });
      setNotice(r.has_rule ? "초대를 등록했습니다." : "초대를 등록했지만 접근 규칙이 없습니다. '접근 규칙' 탭에서 규칙을 추가하세요.");
      setEmail(""); setMemo(""); setDays(7);
      await load();
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  const revoke = async (i: Invitation) => {
    if (!window.confirm(`${i.email} 초대를 취소할까요?`)) return;
    setErr(""); setNotice("");
    try { await revokeInvitation(i.id); await load(); } catch (e) { setErr(errMsg(e)); }
  };

  return (
    <div>
      {err && <div style={errStyle}>{err}</div>}
      {notice && <div style={warnStyle}>{notice}</div>}

      <h3>계정 목록</h3>
      <table style={{ borderCollapse: "collapse", width: "100%", marginBottom: 24 }}>
        <thead><tr>
          <th style={cell}>이메일</th><th style={cell}>권한셋</th><th style={cell}>가입일</th>
          <th style={cell}>최근 로그인</th><th style={cell}>상태</th><th style={cell}></th>
        </tr></thead>
        <tbody>
          {accounts.map((a) => (
            <tr key={a.id} style={{ opacity: a.active ? 1 : 0.5 }}>
              <td style={cell}>{a.email}{a.is_super && <b style={{ marginLeft: 6, color: "#7c3aed" }}>마스터</b>}</td>
              <td style={cell}>{a.permission_set_name ?? <span style={{ color: "#c0392b" }}>규칙 없음</span>}</td>
              <td style={cell}>{fmtDate(a.activated_at)}</td>
              <td style={cell}>{fmtDate(a.last_login_at)}</td>
              <td style={cell}>{a.active ? "활성" : "비활성"}</td>
              <td style={cell}>
                <button onClick={() => toggle(a)} disabled={a.is_super && a.active}
                  title={a.is_super ? "마스터 계정은 비활성화할 수 없습니다" : ""}>
                  {a.active ? "비활성화" : "활성화"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>초대 등록</h3>
      <div style={box}>
        <label>이메일 <input value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder="name@lunchlab.me" style={{ width: 240 }} /></label>{" "}
        <label>유효기간 <input type="number" min={1} max={30} value={days}
          onChange={(e) => setDays(Number(e.target.value))} style={{ width: 60 }} />일</label>{" "}
        <label>메모 <input value={memo} onChange={(e) => setMemo(e.target.value)} style={{ width: 200 }} /></label>{" "}
        <button onClick={invite} disabled={busy || !email.trim()}>{busy ? "등록 중…" : "초대"}</button>
        {noRule && <div style={warnStyle}>⚠ 이 이메일에 맞는 활성 접근 규칙이 없습니다. 규칙이 없으면 로그인해도 가입되지 않습니다.</div>}
      </div>

      <h3>초대 목록</h3>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr>
          <th style={cell}>이메일</th><th style={cell}>상태</th><th style={cell}>규칙</th>
          <th style={cell}>초대일</th><th style={cell}>만료일</th><th style={cell}>메모</th><th style={cell}></th>
        </tr></thead>
        <tbody>
          {invites.map((i) => (
            <tr key={i.id}>
              <td style={cell}>{i.email}</td>
              <td style={{ ...cell, color: STATE_COLORS[i.state], fontWeight: 600 }}>{STATE_LABELS[i.state]}</td>
              <td style={cell}>{i.has_rule ? "있음" : <span style={{ color: "#c0392b" }}>없음</span>}</td>
              <td style={cell}>{fmtDate(i.created_at)}</td>
              <td style={cell}>{fmtDate(i.expires_at)}</td>
              <td style={cell}>{i.memo ?? ""}</td>
              <td style={cell}>{i.state === "pending" && <button onClick={() => revoke(i)}>취소</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
