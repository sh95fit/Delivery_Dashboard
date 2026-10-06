import { useEffect, useMemo, useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { nowHms } from "@/components/ui/SaveNote";
import { useMe } from "@/layouts/shell";
import { listManagers } from "@/api/masters";
import type { ManagerRow } from "@/api/masters";
import { INCOME_LABEL, listWorkers, needsName, otText, rateText, workText } from "@/api/workers";
import type { WorkerRow } from "@/api/workers";
import { errText } from "@/lib/form";
import { num } from "@/lib/format";
import WorkerEditor from "./WorkerEditor";
import WorkerImport from "./WorkerImport";

type View = "active" | "inactive" | "all";
const VIEWS: Array<[View, string]> = [["active", "활성"], ["inactive", "비활성"], ["all", "전체"]];

export default function WorkersPage() {
  const isAdmin = Boolean(useMe()?.is_admin);
  const [rows, setRows] = useState<WorkerRow[]>([]);
  const [managers, setManagers] = useState<ManagerRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [view, setView] = useState<View>("active");
  const [sel, setSel] = useState<number | "new" | null>(null);
  const [created, setCreated] = useState<number | null>(null);
  const [lastSaved, setLastSaved] = useState<{ id: number; at: string } | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [imported, setImported] = useState("");

  async function reload() {
    try {
      const [w, m] = await Promise.all([listWorkers(), listManagers()]);
      setRows(w.items);
      setManagers(m.items);
      setError("");
    } catch (e) {
      setError(errText(e));
      throw e;
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { reload().catch(() => {}); }, []);

  const counts = useMemo(() => ({
    active: rows.filter((r) => r.active).length,
    inactive: rows.filter((r) => !r.active).length,
    all: rows.length,
  }), [rows]);

  const shown = useMemo(() => {
    const k = q.trim();
    return rows
      .filter((r) => (view === "all" || r.active === (view === "active")) &&
        (!k || r.name.includes(k) || (r.account?.manager_name ?? "").includes(k)))
      .sort((a, b) => Number(b.active) - Number(a.active) ||
        Number(needsName(b)) - Number(needsName(a)) ||
        a.name.localeCompare(b.name, "ko", { numeric: true }));
  }, [rows, view, q]);

  const nameTodo = rows.filter((r) => r.active && needsName(r)).length;
  const noRate = rows.filter((r) => r.active && !r.rate).length;
  const selRow = typeof sel === "number" ? rows.find((r) => r.id === sel) ?? null : null;

  return (
    <PageLayout title="인력">
      <div className="notice">
        실제 근무하는 <b>사람</b> 단위로 계약 조건(급여·지정 출퇴근·휴게·초과수당·부가세)과 <b>고정 사용 계정</b>을 관리합니다.
        정규직은 월급(+인센티브), 그 외는 시급제입니다. 모든 변경은 <b>적용 시작일</b>부터 반영되고 이전 기간은 당시 조건으로 계산됩니다.
      </div>

      {error && <div className="mt"><ErrorBox message={error} /></div>}

      <Panel
        title={`인력 ${num(shown.length)}명`}
        right={
          <>
            {nameTodo > 0 && <Chip tone="caution">이름 정리 필요 {num(nameTodo)}명</Chip>}
            {noRate > 0 && <Chip tone="caution">계약 미입력 {num(noRate)}명</Chip>}
            <div className="seg">
              {VIEWS.map(([k, label]) => (
                <button key={k} type="button" className={view === k ? "on" : undefined} onClick={() => setView(k)}>
                  {label} {num(counts[k])}
                </button>
              ))}
            </div>
            <input className="input input-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="이름·계정 검색" />
            {isAdmin && <Button size="sm" onClick={() => setImportOpen(true)}>일괄 등록</Button>}
            {isAdmin && <Button size="sm" variant="primary" onClick={() => setSel("new")}>인력 추가</Button>}
          </>
        }
      >
        {loading ? (
          <Spinner />
        ) : shown.length === 0 ? (
            rows.length === 0 ? (
                <div className="stack">
                  <div className="muted small">등록된 인력이 없습니다. 근무표 엑셀(시급제)과 운영 계정(정규직·개인 계정)에서 한 번에 등록할 수 있습니다.</div>
                  {isAdmin && <div className="mt"><Button variant="primary" onClick={() => setImportOpen(true)}>일괄 등록 시작</Button></div>}
                </div>
              ) : <div className="muted small">표시할 인력이 없습니다.</div>    
        ) : (
          <DataTable columns={["이름", "구분", "계약(현재)", "지정 근무", "초과수당", "부가세", "고정 계정", "상태", "관리"]}>
            {shown.map((r) => {
              const saved = lastSaved?.id === r.id;
              const cls = [r.active ? "" : "off", saved ? "row-new" : ""].filter(Boolean).join(" ");
              return (
                <tr key={r.id} className={cls || undefined}>
                  <td>
                    {needsName(r) ? <Chip tone="caution">{r.name}</Chip> : r.name}
                    {saved && <span className="save-note ok ml">✓ 저장 {lastSaved!.at}</span>}
                  </td>
                  <td>{INCOME_LABEL[r.income_type] ?? r.income_type}</td>
                  <td>{r.rate ? rateText(r.rate) : <Chip tone="caution">미입력</Chip>}</td>
                  <td>{r.rate ? workText(r.rate) : "-"}</td>
                  <td>{r.rate && r.rate.pay_type === "hourly" ? otText(r.rate) : "-"}</td>
                  <td>{r.rate?.vat_applied ? "포함(10%)" : "-"}</td>
                  <td>
                    {r.account ? (
                      <><span className="dot" style={{ background: r.account.manager_color ?? "#9ca3af" }} /> {r.account.manager_name ?? `#${r.account.manager_id}`}</>
                    ) : <span className="muted">-</span>}
                  </td>
                  <td>{r.active ? <Chip tone="ok">활성</Chip> : <Chip>비활성</Chip>}</td>
                  <td><Button size="sm" onClick={() => setSel(r.id)}>{isAdmin ? "편집" : "보기"}</Button></td>
                </tr>
              );
            })}
          </DataTable>
        )}
      </Panel>

      {(sel === "new" || selRow) && (
        <WorkerEditor
          key={sel === "new" ? "new" : String(sel)}
          row={selRow}
          workers={rows}
          managers={managers}
          isAdmin={isAdmin}
          justCreated={selRow !== null && created === selRow.id}
          onChanged={async (id, isCreated) => {
            await reload();
            setLastSaved({ id, at: nowHms() });
            if (isCreated) {
              setCreated(id);
              setSel(id);
            }
          }}
          onClose={() => { setSel(null); setCreated(null); }}
        />
      )}
      {imported && <div className="mt"><span className="save-note ok">✓ {imported}</span></div>}
      {importOpen && (
        <WorkerImport
          managers={managers}
          onDone={async (n) => {
            await reload();
            setImported(`${n}명 등록됨 · ${nowHms()} — '계약 미입력' 칩이 있으면 이어서 입력하세요`);
          }}
          onClose={() => setImportOpen(false)}
        />
      )}
    </PageLayout>
  );
}
