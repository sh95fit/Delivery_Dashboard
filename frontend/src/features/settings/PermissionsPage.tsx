import { useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import {
  OPS, OP_LABELS, PAGE_KEYS, PAGE_LABELS, cleanGrants, toggleOp,
  listSets, createSet, updateSet, deleteSet,
  type PermissionSet, type CleanGrants,
} from "@/api/permissions";
import UsersTab from "./UsersTab";

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));

type Tab = "sets" | "users";

export default function PermissionsPage() {
  const [tab, setTab] = useState<Tab>("users");
  const tabBtn = (k: Tab, label: string) => (
    <button className={`tab${tab === k ? " active" : ""}`} onClick={() => setTab(k)}>{label}</button>
  );
  return (
    <>
      <header className="topbar"><h1>권한 관리</h1></header>
      <div className="page">
        <div className="tabs">{tabBtn("users", "사용자")}{tabBtn("sets", "권한셋")}</div>
        {tab === "users" && <UsersTab />}
        {tab === "sets" && <SetsTab />}
      </div>
    </>
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
    <>
      {err && <p className="error-box mt">{err}</p>}

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">권한셋 목록</h2>
          <div className="panel-right">
            <button className="btn btn-primary" onClick={() => startEdit(null)}>+ 새 권한셋</button>
          </div>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr>
              <th>이름</th><th>메모</th><th className="num">사용자 수</th><th>구분</th><th>동작</th>
            </tr></thead>
            <tbody>
              {sets.map((s) => {
                const blockReason = s.builtin ? "기본 제공 권한셋은 삭제할 수 없습니다"
                  : s.rule_count > 0 ? `사용자 ${s.rule_count}명이 사용 중입니다` : "";
                return (
                  <tr key={s.id} className={editId === s.id ? "selected" : undefined}>
                    <td>{s.name}</td>
                    <td className="small muted">{s.memo ?? ""}</td>
                    <td className="num">{s.rule_count}</td>
                    <td>
                      <span className={`chip ${s.builtin ? "chip-internal" : "chip-neutral"}`}>
                        {s.builtin ? "기본 제공" : "사용자"}
                      </span>
                    </td>
                    <td>
                      <div className="toolbar">
                        <button className="btn btn-sm" onClick={() => startEdit(s)}>편집</button>
                        <button className="btn btn-sm btn-danger" onClick={() => remove(s)}
                          disabled={Boolean(blockReason)} title={blockReason}>삭제</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {sets.length === 0 && <tr><td colSpan={5} className="muted">권한셋이 없습니다</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {editId !== null && (
        <section className="panel">
          <div className="panel-head">
            <h2 className="panel-title">{editId === "new" ? "새 권한셋" : "권한셋 편집"}</h2>
          </div>
          <p className="panel-desc">보기(R)를 끄면 생성·수정·삭제도 함께 꺼집니다.</p>
          <div className="form-row">
            <input className="input" placeholder="이름" value={name} maxLength={50}
              onChange={(e) => setName(e.target.value)} />
            <input className="input grow" placeholder="메모(선택)" value={memo}
              onChange={(e) => setMemo(e.target.value)} />
          </div>
          <div className="tbl-wrap mt">
            <table className="tbl perm-grid">
              <thead><tr>
                <th>화면</th>
                {OPS.map((op) => <th key={op} className="center">{OP_LABELS[op]}</th>)}
              </tr></thead>
              <tbody>
                {PAGE_KEYS.map((k) => (
                  <tr key={k}>
                    <td>{PAGE_LABELS[k]}</td>
                    {OPS.map((op) => (
                      <td key={op} className="center">
                        <input type="checkbox" checked={grants[k][op]}
                          aria-label={`${PAGE_LABELS[k]} ${OP_LABELS[op]}`}
                          onChange={() => setGrants((g) => toggleOp(g, k, op))} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="toolbar mt">
            <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "저장 중…" : "저장"}</button>
            <button className="btn" onClick={() => setEditId(null)} disabled={busy}>취소</button>
          </div>
        </section>
      )}
    </>
  );
}
