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
import { OPS_LABEL, listManagers } from "@/api/masters";
import type { ManagerRow } from "@/api/masters";
import { errText } from "@/lib/form";
import { num } from "@/lib/format";
import ManagerEditor from "./ManagerEditor";

type View = "active" | "inactive" | "all";
const VIEWS: Array<[View, string]> = [["active", "운영 활성"], ["inactive", "운영 비활성"], ["all", "전체"]];
const VIEW_KEY = "ll.managers.view";

const opsOn = (r: ManagerRow) => r.ops_status === "active";

export function OpsChip({ r }: { r: ManagerRow }) {
  const label = OPS_LABEL[r.ops_status] ?? r.ops_status;
  const title = `운영 DB status: ${r.ops_status_raw ?? "(없음)"}`;
  return (
    <span title={title}>
      {r.ops_status === "active" ? <Chip tone="ok">{label}</Chip>
        : r.ops_status === "unknown" ? <Chip tone="caution">{label}</Chip>
        : <Chip>{label}</Chip>}
    </span>
  );
}

export default function ManagersPage() {
  const isAdmin = Boolean(useMe()?.is_admin);
  const [rows, setRows] = useState<ManagerRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [lastSaved, setLastSaved] = useState<{ id: number; at: string } | null>(null);
  const [view, setView] = useState<View>(() => {
    try {
      const v = localStorage.getItem(VIEW_KEY);
      return VIEWS.some(([k]) => k === v) ? (v as View) : "active";
    } catch {
      return "active";
    }
  });

  async function reload() {
    try {
      const m = await listManagers();
      setRows(m.items);
      setError("");
    } catch (e) {
      setError(errText(e));
      throw e;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload().catch(() => {}); }, []);
  useEffect(() => {
    try { localStorage.setItem(VIEW_KEY, view); } catch { /* 무시 */ }
  }, [view]);

  const counts = useMemo(() => ({
    active: rows.filter(opsOn).length,
    inactive: rows.filter((r) => !opsOn(r)).length,
    all: rows.length,
  }), [rows]);

  const shown = useMemo(() => {
    const k = q.trim();
    return rows
      .filter((r) => (view === "all" || opsOn(r) === (view === "active")) &&
        (!k || (r.name ?? "").includes(k) || r.workers.some((w) => w.includes(k))))
      .sort((a, b) =>
        Number(opsOn(b)) - Number(opsOn(a)) ||
        Number(b.active) - Number(a.active) ||
        (a.name ?? "").localeCompare(b.name ?? "", "ko", { numeric: true }));
  }, [rows, view, q]);

  const mismatch = rows.filter((r) => !opsOn(r) && r.active).length;
  const selRow = rows.find((r) => r.manager_id === sel) ?? null;

  return (
    <PageLayout title="매니저 계정">
      <div className="notice">
        계정은 운영 앱의 <b>배송 기록 단위</b>(배송지·완료 시각·매출)입니다. 이름·색·<b>운영 상태</b>는 운영 DB에서 가져오고(여기서 변경 불가),
        여기서는 <b>대시보드 상태·메모</b>만 관리합니다. 급여·계약 조건·고정 사용 계정은 <b>인력</b>, 차량 비용은 <b>차량·지출</b>에서 관리하며,
        물류비는 날짜별로 <b>계정 → 그날 담당 인력 → 그 인력의 차량</b> 순서로 연결해 계산합니다.
      </div>

      {error && <div className="mt"><ErrorBox message={error} /></div>}

      <Panel
        title={`매니저 ${num(shown.length)}명`}
        right={
          <>
            {mismatch > 0 && (
              <button type="button" className="chip-btn" onClick={() => setView("inactive")}
                title="운영 DB에서는 비활성인데 대시보드는 활성인 매니저">
                <Chip tone="caution">상태 불일치 {num(mismatch)}명</Chip>
              </button>
            )}
            <div className="seg">
              {VIEWS.map(([k, label]) => (
                <button key={k} type="button" className={view === k ? "on" : undefined} onClick={() => setView(k)}>
                  {label} {num(counts[k])}
                </button>
              ))}
            </div>
            <input className="input input-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="계정·인력 검색" />
          </>
        }
      >
        {loading ? (
          <Spinner />
        ) : shown.length === 0 ? (
          <div className="muted small">표시할 매니저가 없습니다.</div>
        ) : (
          <DataTable columns={["매니저", "운영 상태", "대시보드", "고정 사용 인력", "메모", "관리"]}>
            {shown.map((r) => {
              const saved = lastSaved?.id === r.manager_id;
              const cls = [opsOn(r) && r.active ? "" : "off", saved ? "row-new" : ""].filter(Boolean).join(" ");
              return (
                <tr key={r.manager_id} className={cls || undefined}>
                  <td>
                    <span className="dot" style={{ background: r.color ?? "#9ca3af" }} /> {r.name ?? `#${r.manager_id}`}
                    {saved && <span className="save-note ok ml">✓ 수정 {lastSaved!.at}</span>}
                  </td>
                  <td><OpsChip r={r} /></td>
                  <td>
                    {r.active ? <Chip tone="ok">활성</Chip> : <Chip>비활성</Chip>}
                    {!opsOn(r) && r.active && <span className="muted small" title="운영 비활성 계정"> ⚠</span>}
                  </td>
                  <td>{r.workers.length ? r.workers.join(", ") : <span className="muted">-</span>}</td>
                  <td className="small">{r.memo ?? <span className="muted">-</span>}</td>
                  <td><Button size="sm" onClick={() => setSel(r.manager_id)}>{isAdmin ? "편집" : "보기"}</Button></td>
                </tr>
              );
            })}
          </DataTable>
        )}
      </Panel>

      {selRow && (
        <ManagerEditor
          key={selRow.manager_id}
          row={selRow}
          isAdmin={isAdmin}
          onChanged={async () => {
            await reload();
            setLastSaved({ id: selRow.manager_id, at: nowHms() });
          }}
          onClose={() => setSel(null)}
        />
      )}
    </PageLayout>
  );
}
