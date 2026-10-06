import { useEffect, useMemo, useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { useMe } from "@/layouts/shell";
import { OPS_LABEL, listManagers, listVehicles, payText, scheduleText } from "@/api/masters";
import type { ManagerRow, Vehicle } from "@/api/masters";
import { errText } from "@/lib/form";
import { num, won } from "@/lib/format";
import ManagerEditor, { nowHms } from "./ManagerEditor";

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
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
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
      const [m, v] = await Promise.all([listManagers(), listVehicles()]);
      setRows(m.items);
      setVehicles(v.items);
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
      .filter((r) => (view === "all" || opsOn(r) === (view === "active")) && (!k || (r.name ?? "").includes(k)))
      .sort((a, b) =>
        Number(opsOn(b)) - Number(opsOn(a)) ||
        Number(b.active) - Number(a.active) ||
        (a.name ?? "").localeCompare(b.name ?? "", "ko", { numeric: true }));
  }, [rows, view, q]);

  const missingPay = rows.filter((r) => opsOn(r) && r.active && !r.pay).length;
  const mismatch = rows.filter((r) => !opsOn(r) && r.active).length;
  const selRow = rows.find((r) => r.manager_id === sel) ?? null;

  return (
    <PageLayout title="매니저">
      <div className="notice">
        이름·색·<b>운영 상태</b>는 운영 DB에서 가져옵니다(여기서 변경 불가). <b>대시보드 상태·급여·근무 기준·차량 배정</b>은 여기서 관리합니다.
        시급제의 근무 시작·종료·휴게는 <b>예상 물류비</b> 산출 기준이며, 실제 비용은 이후 근무일지(출퇴근 기록)로 보정합니다.
      </div>

      {error && <div className="mt"><ErrorBox message={error} /></div>}

      <Panel
        title={`매니저 ${num(shown.length)}명`}
        right={
          <>
            {missingPay > 0 && <Chip tone="caution">급여 미입력 {num(missingPay)}명</Chip>}
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
            <input className="input input-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="이름 검색" />
          </>
        }
      >
        {loading ? (
          <Spinner />
        ) : shown.length === 0 ? (
          <div className="muted small">표시할 매니저가 없습니다.</div>
        ) : (
          <DataTable columns={["매니저", "운영 상태", "대시보드", "급여(현재)", "근무 기준",
            { label: "예상 일 인건비", num: true }, "차량(현재)", "관리"]}>
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
                  <td>{r.pay ? payText(r.pay) : <Chip tone="caution">미입력</Chip>}</td>
                  <td>{r.pay ? scheduleText(r.pay) : "-"}</td>
                  <td className="num">{r.pay?.daily_cost != null ? won(r.pay.daily_cost) : <span className="muted">-</span>}</td>
                  <td>{r.vehicle ? r.vehicle.plate_no : <span className="muted">-</span>}</td>
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
          vehicles={vehicles}
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
