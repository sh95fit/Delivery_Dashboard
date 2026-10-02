import { useEffect, useMemo, useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { useMe } from "@/layouts/shell";
import { listManagers, listVehicles, PAY_LABEL } from "@/api/masters";
import type { ManagerRow, PayRate, Vehicle } from "@/api/masters";
import { errText } from "@/lib/form";
import { num, won } from "@/lib/format";
import ManagerEditor from "./ManagerEditor";

const RECENT_KEY = "ll.managers.recentOnly";

const payText = (p: PayRate) => (p.pay_type === "none" ? PAY_LABEL.none : `${PAY_LABEL[p.pay_type]} ${won(p.amount)}`);

export default function ManagersPage() {
  const isAdmin = Boolean(useMe()?.is_admin);
  const [rows, setRows] = useState<ManagerRow[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [recentOnly, setRecentOnly] = useState(() => {
    try { return localStorage.getItem(RECENT_KEY) !== "0"; } catch { return true; }
  });

  async function reload() {
    try {
      const [m, v] = await Promise.all([listManagers(), listVehicles()]);
      setRows(m.items);
      setVehicles(v.items);
      setError("");
    } catch (e) {
      setError(errText(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload().catch(() => {}); }, []);
  useEffect(() => {
    try { localStorage.setItem(RECENT_KEY, recentOnly ? "1" : "0"); } catch { /* 무시 */ }
  }, [recentOnly]);

  const shown = useMemo(() => {
    const k = q.trim();
    return rows
      .filter((r) => (!recentOnly || r.recent_stops > 0) && (!k || (r.name ?? "").includes(k)))
      .sort((a, b) =>
        Number(b.active) - Number(a.active) ||
        b.recent_stops - a.recent_stops ||
        (a.name ?? "").localeCompare(b.name ?? "", "ko", { numeric: true }));
  }, [rows, recentOnly, q]);

  const missingPay = rows.filter((r) => r.active && r.recent_stops > 0 && !r.pay).length;
  const selRow = rows.find((r) => r.manager_id === sel) ?? null;

  return (
    <PageLayout title="매니저">
      <div className="notice">
        이름·색은 운영 DB에서 가져오고, <b>급여·차량 배정</b>은 여기서 관리합니다.
        급여·차량은 <b>적용 시작일</b> 기준 이력으로 저장되어, 변경해도 과거 날짜 비용은 당시 기준으로 계산됩니다.
      </div>

      {error && <div className="mt"><ErrorBox message={error} /></div>}

      <Panel
        title={`매니저 ${num(shown.length)}명`}
        right={
          <>
            {missingPay > 0 && <Chip tone="caution">급여 미입력 {num(missingPay)}명</Chip>}
            <label className="check">
              <input type="checkbox" checked={recentOnly} onChange={(e) => setRecentOnly(e.target.checked)} />
              최근 30일 배송 매니저만
            </label>
            <input className="input input-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="이름 검색" />
          </>
        }
      >
        {loading ? (
          <Spinner />
        ) : shown.length === 0 ? (
          <div className="muted small">표시할 매니저가 없습니다.</div>
        ) : (
          <DataTable columns={["매니저", { label: "최근 30일", num: true }, "급여(현재)", "차량(현재)", "상태", "관리"]}>
            {shown.map((r) => (
              <tr key={r.manager_id} className={r.active ? undefined : "off"}>
                <td>
                  <span className="dot" style={{ background: r.color ?? "#9ca3af" }} /> {r.name ?? `#${r.manager_id}`}
                </td>
                <td className="num">{r.recent_stops ? `${num(r.recent_stops)}건` : "-"}</td>
                <td>{r.pay ? payText(r.pay) : <Chip tone="caution">미입력</Chip>}</td>
                <td>{r.vehicle ? r.vehicle.plate_no : <span className="muted">-</span>}</td>
                <td>{r.active ? <Chip tone="ok">사용</Chip> : <Chip>중지</Chip>}</td>
                <td>
                  <Button size="sm" onClick={() => setSel(r.manager_id)}>{isAdmin ? "편집" : "보기"}</Button>
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>

      {selRow && (
        <ManagerEditor
          key={selRow.manager_id}
          row={selRow}
          vehicles={vehicles}
          isAdmin={isAdmin}
          onChanged={reload}
          onClose={() => setSel(null)}
        />
      )}
    </PageLayout>
  );
}
