import { useEffect, useState, type CSSProperties } from "react";
import { ApiError } from "@/api/client";
import {
  OPS, OP_LABELS, PAGE_KEYS, PAGE_LABELS, cleanGrants, toggleOp,
  listSets, createSet, updateSet, deleteSet,
  type PermissionSet, type CleanGrants,
} from "@/api/permissions";
import UsersTab from "./UsersTab";

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));
const cell: CSSProperties = { border: "1px solid #ddd", padding: "6px 8px", textAlign: "left" };
const box: CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 };
const errStyle: CSSProperties = { color: "#c0392b", margin: "8px 0" };

type Tab = "sets" | "users";

export default function PermissionsPage() {
  const [tab, setTab] = useState<Tab>("users");
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
        {tabBtn("users", "사용자")}{tabBtn("sets", "권한셋")}
      </div>
      {tab === "users" && <UsersTab />}
      {tab === "sets" && <SetsTab />}
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
          <th style={cell}>이름</th><th style={cell}>메모</th><th style={cell}>사용자 수</th>
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
