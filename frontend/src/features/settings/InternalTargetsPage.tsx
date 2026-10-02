import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import PageLayout from "@/layouts/PageLayout";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { useMe } from "@/layouts/shell";
import { addInternalTarget, deleteInternalTarget, listInternalTargets, searchInternalTargets } from "@/api/internalTargets";
import type { InternalTarget, TargetCandidate, TargetKind } from "@/api/internalTargets";
import { kstDateTime } from "@/lib/format";

const KIND_LABEL: Record<TargetKind, string> = { address: "배송지", account: "고객사" };
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const targetName = (t: InternalTarget) => t.name ?? t.label ?? `ID ${t.target_id}`;

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
      setItems((await listInternalTargets()).items);
    } catch (err) {
      setError(errText(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload().catch(() => {});
  }, []);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  function onSearch(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    run(async () => setResults((await searchInternalTargets(kind, q.trim())).items));
  }

  function onAdd(c: TargetCandidate) {
    run(async () => {
      await addInternalTarget({ kind, target_id: c.id, memo: memo.trim() || null });
      setMemo("");
      setResults((rs) => rs?.map((x) => (x.id === c.id ? { ...x, registered: true } : x)) ?? null);
      await reload();
    });
  }

  function onDelete(t: InternalTarget) {
    const ok = window.confirm(
      `${KIND_LABEL[t.kind]} '${targetName(t)}'을(를) 직원식 대상에서 해제할까요?\n모든 날짜의 매출에 다시 포함됩니다.`,
    );
    if (!ok) return;
    run(async () => {
      await deleteInternalTarget(t.id);
      setResults((rs) => rs?.map((x) => (t.kind === kind && x.id === t.target_id ? { ...x, registered: false } : x)) ?? null);
      await reload();
    });
  }

  return (
    <PageLayout title="직원식 대상 설정">
      <div className="notice notice-internal">
        여기 지정한 배송지·고객사의 주문은 <b>배송 일감·식수에는 그대로 포함</b>되고,{" "}
        <b>매출(총금액·환불·순매출)에서만 빠져</b> 대시보드 하단 '직원식' 블록에 수량·금액으로 따로 표시됩니다.
        <br />
        변경은 과거 날짜를 포함한 모든 날짜에 적용되며, 반영까지 최대 30초 걸립니다. 고객사로 지정하면 그 고객사의 모든 배송지가 대상이 됩니다.
      </div>

      {error && <div className="mt"><ErrorBox message={error} /></div>}

      <Panel title={`현재 대상 ${items.length}건`}>
        {loading ? (
          <Spinner />
        ) : items.length === 0 ? (
          <div className="muted small">지정된 직원식 대상이 없습니다. 모든 주문이 매출에 포함됩니다.</div>
        ) : (
          <DataTable columns={["구분", "ID", "이름", "소속 고객사", "메모", "등록", ...(isAdmin ? ["관리"] : [])]}>
            {items.map((t) => (
              <tr key={t.id}>
                <td><Chip tone="internal">{KIND_LABEL[t.kind]}</Chip></td>
                <td>{t.target_id}</td>
                <td>{targetName(t)}</td>
                <td>{t.kind === "address" ? t.account_name ?? "-" : "-"}</td>
                <td>{t.memo ?? ""}</td>
                <td>
                  {t.created_by ?? "-"}
                  <div className="muted small">{kstDateTime(t.created_at)}</div>
                </td>
                {isAdmin && (
                  <td><Button size="sm" variant="danger" disabled={busy} onClick={() => onDelete(t)}>해제</Button></td>
                )}
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>

      {isAdmin ? (
        <Panel title="대상 추가">
          <form onSubmit={onSearch} className="form-row">
            <select className="input" value={kind} onChange={(e) => { setKind(e.target.value as TargetKind); setResults(null); }}>
              <option value="address">배송지</option>
              <option value="account">고객사</option>
            </select>
            <input className="input grow" value={q} onChange={(e) => setQ(e.target.value)}
              placeholder={kind === "address" ? "배송지명 · 고객사명 · 주소ID" : "고객사명 · 고객사ID"} />
            <input className="input grow" value={memo} onChange={(e) => setMemo(e.target.value)}
              placeholder="메모 (예: 현장 수령, 파트타이머 2,000원)" maxLength={200} />
            <Button type="submit" variant="primary" disabled={busy || !q.trim()}>검색</Button>
          </form>

          {results &&
            (results.length === 0 ? (
              <div className="muted small mt">검색 결과가 없습니다.</div>
            ) : (
              <div className="mt">
                <DataTable columns={kind === "address" ? ["주소ID", "배송지", "고객사", "선택"] : ["고객사ID", "고객사", "배송지 수", "선택"]}>
                  {results.map((c) => (
                    <tr key={c.id}>
                      <td>{c.id}</td>
                      <td>{c.name ?? "-"}</td>
                      <td>{kind === "address" ? `${c.account_name ?? "-"} (${c.account_id ?? "-"})` : c.address_count ?? 0}</td>
                      <td>
                        {c.registered ? (
                          <Chip tone="internal">등록됨</Chip>
                        ) : (
                          <Button size="sm" disabled={busy} onClick={() => onAdd(c)}>추가</Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </DataTable>
              </div>
            ))}
        </Panel>
      ) : (
        <Panel><div className="muted small">대상 추가·해제는 관리자만 할 수 있습니다.</div></Panel>
      )}
    </PageLayout>
  );
}
