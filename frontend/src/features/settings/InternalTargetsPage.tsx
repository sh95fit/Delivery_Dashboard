import { useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import PageLayout from "@/layouts/PageLayout";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { useMe } from "@/layouts/shell";
import {
  addInternalTarget,
  deleteInternalTarget,
  listInternalTargets,
  searchInternalTargets,
} from "@/api/internalTargets";
import type { InternalTarget, TargetCandidate, TargetKind } from "@/api/internalTargets";
import { kstDateTime } from "@/lib/format";

const KIND_LABEL: Record<TargetKind, string> = { address: "배송지", account: "고객사" };
const td: CSSProperties = { padding: "8px 10px", borderBottom: "1px solid #f0f0f0", fontSize: 14 };
const box: CSSProperties = {
  border: "1px solid #e5e7eb", borderRadius: 10, padding: 16, background: "#fff", marginTop: 16,
};
const btn: CSSProperties = { padding: "4px 10px", fontSize: 13, cursor: "pointer" };

function errText(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

function targetName(t: InternalTarget) {
  return t.name ?? t.label ?? `ID ${t.target_id}`;
}

export default function InternalTargetsPage() {
  const isAdmin = Boolean(useMe()?.is_admin);
  const [items, setItems] = useState<InternalTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [kind, setKind] = useState<TargetKind>("address");
  const [q, setQ] = useState("");
  const [memo, setMemo] = useState("");
  const [results, setResults] = useState<TargetCandidate[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const r = await listInternalTargets();
      setItems(r.items);
    } catch (err) {
      setError(errText(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload().catch(() => {});
  }, []);

  async function onSearch(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError("");
    try {
      const r = await searchInternalTargets(kind, q.trim());
      setResults(r.items);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  async function onAdd(c: TargetCandidate) {
    setBusy(true);
    setError("");
    try {
      await addInternalTarget({ kind, target_id: c.id, memo: memo.trim() || null });
      setMemo("");
      setResults((rs) => rs?.map((x) => (x.id === c.id ? { ...x, registered: true } : x)) ?? null);
      await reload();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(t: InternalTarget) {
    const ok = window.confirm(
      `${KIND_LABEL[t.kind]} '${targetName(t)}'을(를) 직원식 대상에서 해제할까요?\n모든 날짜의 매출에 다시 포함됩니다.`,
    );
    if (!ok) return;
    setBusy(true);
    setError("");
    try {
      await deleteInternalTarget(t.id);
      setResults((rs) =>
        rs?.map((x) => (t.kind === kind && x.id === t.target_id ? { ...x, registered: false } : x)) ?? null,
      );
      await reload();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  const listColumns = ["구분", "ID", "이름", "소속 고객사", "메모", "등록", ...(isAdmin ? ["관리"] : [])];

  return (
    <PageLayout title="직원식 설정">
      <div style={{ ...box, marginTop: 0, background: "#faf5ff", borderColor: "#ddd6fe", fontSize: 13, lineHeight: 1.7 }}>
        여기 지정한 배송지·고객사의 주문은 <b>배송 일감·식수에는 그대로 포함</b>되고,{" "}
        <b>매출(총금액·환불·순매출)에서만 빠져</b> 대시보드 하단 '직원식' 블록에 수량·금액으로 따로 표시됩니다.
        <br />
        변경은 과거 날짜를 포함한 모든 날짜에 적용되며, 반영까지 최대 30초 걸립니다. 고객사로 지정하면 그 고객사의 모든 배송지가 대상이 됩니다.
      </div>

      {error && (
        <div style={{ marginTop: 16 }}>
          <ErrorBox message={error} />
        </div>
      )}

      <section style={box}>
        <h2 style={{ fontSize: 16, margin: "0 0 12px" }}>현재 대상 {items.length}건</h2>
        {loading ? (
          <Spinner />
        ) : items.length === 0 ? (
          <div style={{ color: "#888", fontSize: 13 }}>지정된 직원식 대상이 없습니다. 모든 주문이 매출에 포함됩니다.</div>
        ) : (
          <DataTable columns={listColumns}>
            {items.map((t) => (
              <tr key={t.id}>
                <td style={td}>{KIND_LABEL[t.kind]}</td>
                <td style={td}>{t.target_id}</td>
                <td style={td}>{targetName(t)}</td>
                <td style={td}>{t.kind === "address" ? t.account_name ?? "-" : "-"}</td>
                <td style={td}>{t.memo ?? ""}</td>
                <td style={td}>
                  {t.created_by ?? "-"}
                  <br />
                  <span style={{ color: "#888", fontSize: 12 }}>{kstDateTime(t.created_at)}</span>
                </td>
                {isAdmin && (
                  <td style={td}>
                    <button style={btn} disabled={busy} onClick={() => onDelete(t)}>해제</button>
                  </td>
                )}
              </tr>
            ))}
          </DataTable>
        )}
      </section>

      {isAdmin ? (
        <section style={box}>
          <h2 style={{ fontSize: 16, margin: "0 0 12px" }}>대상 추가</h2>
          <form onSubmit={onSearch} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as TargetKind);
                setResults(null);
              }}
            >
              <option value="address">배송지</option>
              <option value="account">고객사</option>
            </select>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={kind === "address" ? "배송지명 · 고객사명 · 주소ID" : "고객사명 · 고객사ID"}
              style={{ minWidth: 240 }}
            />
            <input
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              placeholder="메모 (예: 현장 수령, 파트타이머 2,000원)"
              maxLength={200}
              style={{ minWidth: 280 }}
            />
            <button type="submit" style={btn} disabled={busy || !q.trim()}>검색</button>
          </form>

          {results &&
            (results.length === 0 ? (
              <div style={{ color: "#888", fontSize: 13, marginTop: 12 }}>검색 결과가 없습니다.</div>
            ) : (
              <div style={{ marginTop: 12 }}>
                <DataTable
                  columns={kind === "address" ? ["주소ID", "배송지", "고객사", "선택"] : ["고객사ID", "고객사", "배송지 수", "선택"]}
                >
                  {results.map((c) => (
                    <tr key={c.id}>
                      <td style={td}>{c.id}</td>
                      <td style={td}>{c.name ?? "-"}</td>
                      <td style={td}>
                        {kind === "address" ? `${c.account_name ?? "-"} (${c.account_id ?? "-"})` : c.address_count ?? 0}
                      </td>
                      <td style={td}>
                        {c.registered ? (
                          <span style={{ color: "#7c3aed", fontSize: 12, fontWeight: 600 }}>등록됨</span>
                        ) : (
                          <button style={btn} disabled={busy} onClick={() => onAdd(c)}>추가</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </DataTable>
              </div>
            ))}
        </section>
      ) : (
        <div style={{ ...box, color: "#888", fontSize: 13 }}>대상 추가·해제는 관리자만 할 수 있습니다.</div>
      )}
    </PageLayout>
  );
}
