import { useEffect, useState, type CSSProperties } from "react";
import { ApiError } from "@/api/client";
import {
  OPS, OP_LABELS, PAGE_KEYS, PAGE_LABELS, cleanGrants, toggleOp,
  listSets, createSet, updateSet, deleteSet,
  listRules, createRule, updateRule, deleteRule,
  type PermissionSet, type AccessRule, type CleanGrants, type RuleKind,
} from "@/api/permissions";
import UsersTab from "./UsersTab";

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));
const cell: CSSProperties = { border: "1px solid #ddd", padding: "6px 8px", textAlign: "left" };
const box: CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 };
const errStyle: CSSProperties = { color: "#c0392b", margin: "8px 0" };

type Tab = "sets" | "rules" | "accounts";

export default function PermissionsPage() {
  const [tab, setTab] = useState<Tab>("sets");
  const tabBtn = (k: Tab, label: string) => (
    <button
      onClick={() => setTab(k)}
      style={{ padding: "6px 14px", marginRight: 6, fontWeight: tab === k ? 700 : 400,
        borderBottom: tab === k ? "2px solid #333" : "2px solid transparent" }}
    >{label}</button>
  );
  return (
    <div style={{ padding: 16 }}>
      <h2>권한 관리</h2>
      <div style={{ marginBottom: 16 }}>
        {tabBtn("sets", "권한셋")}{tabBtn("rules", "접근 규칙")}{tabBtn("accounts", "계정")}
      </div>
      {tab === "sets" && <SetsTab />}
      {tab === "rules" && <RulesTab />}
      {tab === "accounts" && <UsersTab />}
    </div>
  );
}

/* ───────── 권한셋 탭 ───────── */
function SetsTab() {
  const [sets, setSets] = useState<PermissionSet[]>([]);
  const [err, setErr] = useState("");
  const [editId, setEditId] = useState<number | "new" | null>(null);
  const [name, setName] = useState("");
  const [memo, setMemo] = useState("");
  const [grants, setGrants] = useState<CleanGrants>(cleanGrants({}));
  const [busy, setBusy] = useState(false);

  const load = () => listSets().then(setSets).catch((e) => setErr(errMsg(e)));
  useEffect(() => { load(); }, []);

  const startEdit = (s: PermissionSet | null) => {
    setErr("");
    setEditId(s ? s.id : "new");
    setName(s?.name ?? "");
    setMemo(s?.memo ?? "");
    setGrants(cleanGrants(s?.grants));
  };

  const save = async () => {
    setBusy(true); setErr("");
    try {
      const body = { name, memo: memo.trim() || null, grants: cleanGrants(grants) };
      if (editId === "new") await createSet(body);
      else if (typeof editId === "number") await updateSet(editId, body);
      setEditId(null);
      await load();
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  const remove = async (s: PermissionSet) => {
    if (!window.confirm(`권한셋 "${s.name}"을(를) 삭제할까요?`)) return;
    setErr("");
    try { await deleteSet(s.id); if (editId === s.id) setEditId(null); await load(); }
    catch (e) { setErr(errMsg(e)); }
  };

  return (
    <div>
      {err && <div style={errStyle}>{err}</div>}
      <button onClick={() => startEdit(null)} style={{ marginBottom: 8 }}>+ 새 권한셋</button>
      <table style={{ borderCollapse: "collapse", width: "100%", marginBottom: 16 }}>
        <thead><tr>
          <th style={cell}>이름</th><th style={cell}>메모</th><th style={cell}>사용 규칙 수</th>
          <th style={cell}>구분</th><th style={cell}></th>
        </tr></thead>
        <tbody>
          {sets.map((s) => {
            const blockReason = s.builtin ? "기본 제공 권한셋은 삭제할 수 없습니다"
              : s.rule_count > 0 ? `접근 규칙 ${s.rule_count}개가 사용 중입니다` : "";
            return (
              <tr key={s.id} style={{ background: editId === s.id ? "#f5f8ff" : undefined }}>
                <td style={cell}>{s.name}</td>
                <td style={cell}>{s.memo ?? ""}</td>
                <td style={cell}>{s.rule_count}</td>
                <td style={cell}>{s.builtin ? "기본 제공" : "사용자"}</td>
                <td style={cell}>
                  <button onClick={() => startEdit(s)}>편집</button>{" "}
                  <button onClick={() => remove(s)} disabled={Boolean(blockReason)} title={blockReason}>삭제</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {editId !== null && (
        <div style={box}>
          <h3 style={{ marginTop: 0 }}>{editId === "new" ? "새 권한셋" : "권한셋 편집"}</h3>
          <div style={{ marginBottom: 8 }}>
            <label>이름 <input value={name} maxLength={50} onChange={(e) => setName(e.target.value)} /></label>{" "}
            <label>메모 <input value={memo} onChange={(e) => setMemo(e.target.value)} style={{ width: 300 }} /></label>
          </div>
          <table style={{ borderCollapse: "collapse", marginBottom: 8 }}>
            <thead><tr>
              <th style={cell}>화면</th>
              {OPS.map((op) => <th key={op} style={{ ...cell, textAlign: "center" }}>{op} ({OP_LABELS[op]})</th>)}
            </tr></thead>
            <tbody>
              {PAGE_KEYS.map((k) => (
                <tr key={k}>
                  <td style={cell}>{PAGE_LABELS[k]}</td>
                  {OPS.map((op) => (
                    <td key={op} style={{ ...cell, textAlign: "center" }}>
                      <input type="checkbox" checked={grants[k][op]}
                        onChange={() => setGrants((g) => toggleOp(g, k, op))} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={save} disabled={busy}>{busy ? "저장 중…" : "저장"}</button>{" "}
          <button onClick={() => setEditId(null)} disabled={busy}>취소</button>
        </div>
      )}
    </div>
  );
}

/* ───────── 접근 규칙 탭 ───────── */
type RuleForm = { kind: RuleKind; value: string; permission_set_id: number; active: boolean; memo: string };

function RulesTab() {
  const [rules, setRules] = useState<AccessRule[]>([]);
  const [sets, setSets] = useState<PermissionSet[]>([]);
  const [err, setErr] = useState("");
  const [editId, setEditId] = useState<number | "new" | null>(null);
  const [form, setForm] = useState<RuleForm>({ kind: "email", value: "", permission_set_id: 0, active: true, memo: "" });
  const [busy, setBusy] = useState(false);

  const load = () =>
    Promise.all([listRules(), listSets()])
      .then(([r, s]) => { setRules(r); setSets(s); })
      .catch((e) => setErr(errMsg(e)));
  useEffect(() => { load(); }, []);

  const startEdit = (r: AccessRule | null) => {
    setErr("");
    setEditId(r ? r.id : "new");
    setForm(r
      ? { kind: r.kind, value: r.value, permission_set_id: r.permission_set_id, active: r.active, memo: r.memo ?? "" }
      : { kind: "email", value: "", permission_set_id: sets[0]?.id ?? 0, active: true, memo: "" });
  };

  const save = async () => {
    if (!form.permission_set_id) { setErr("권한셋을 선택하세요"); return; }
    setBusy(true); setErr("");
    try {
      const body = { ...form, memo: form.memo.trim() || null };
      if (editId === "new") await createRule(body);
      else if (typeof editId === "number") await updateRule(editId, body);
      setEditId(null);
      await load();
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  const remove = async (r: AccessRule) => {
    if (!window.confirm(`규칙 "${r.value}"을(를) 삭제할까요?`)) return;
    setErr("");
    try { await deleteRule(r.id); if (editId === r.id) setEditId(null); await load(); }
    catch (e) { setErr(errMsg(e)); }
  };

  return (
    <div>
      {err && <div style={errStyle}>{err}</div>}
      <p style={{ color: "#666", marginTop: 0 }}>이메일 규칙이 도메인 규칙보다 우선합니다.</p>
      <button onClick={() => startEdit(null)} style={{ marginBottom: 8 }} disabled={sets.length === 0}>+ 새 규칙</button>

      {editId !== null && (
        <div style={box}>
          <h3 style={{ marginTop: 0 }}>{editId === "new" ? "새 규칙" : "규칙 편집"}</h3>
          <label>종류{" "}
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as RuleKind })}>
              <option value="email">이메일</option>
              <option value="domain">도메인</option>
            </select>
          </label>{" "}
          <label>값{" "}
            <input value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })}
              placeholder={form.kind === "email" ? "name@lunchlab.me" : "lunchlab.me"} />
          </label>{" "}
          <label>권한셋{" "}
            <select value={form.permission_set_id}
              onChange={(e) => setForm({ ...form, permission_set_id: Number(e.target.value) })}>
              {sets.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>{" "}
          <label><input type="checkbox" checked={form.active}
            onChange={(e) => setForm({ ...form, active: e.target.checked })} /> 활성</label>{" "}
          <label>메모 <input value={form.memo} onChange={(e) => setForm({ ...form, memo: e.target.value })} /></label>
          <div style={{ marginTop: 8 }}>
            <button onClick={save} disabled={busy}>{busy ? "저장 중…" : "저장"}</button>{" "}
            <button onClick={() => setEditId(null)} disabled={busy}>취소</button>
          </div>
        </div>
      )}

      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr>
          <th style={cell}>종류</th><th style={cell}>값</th><th style={cell}>권한셋</th>
          <th style={cell}>상태</th><th style={cell}>메모</th><th style={cell}></th>
        </tr></thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id} style={{ opacity: r.active ? 1 : 0.5 }}>
              <td style={cell}>{r.kind === "email" ? "이메일" : "도메인"}</td>
              <td style={cell}>{r.value}</td>
              <td style={cell}>{r.permission_set_name ?? `#${r.permission_set_id}`}</td>
              <td style={cell}>{r.active ? "활성" : "비활성"}</td>
              <td style={cell}>{r.memo ?? ""}</td>
              <td style={cell}>
                <button onClick={() => startEdit(r)}>편집</button>{" "}
                <button onClick={() => remove(r)}>삭제</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
