import { useEffect, useMemo, useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { useMe } from "@/layouts/shell";
import * as api from "@/api/masters";
import { FUEL_LABEL } from "@/api/masters";
import type { FuelType, ManagerRow, Vehicle, VehicleInput } from "@/api/masters";
import { errText, parseAmount } from "@/lib/form";
import { won } from "@/lib/format";
import { CostSummaryTab, ExpenseTab, PeriodCostTab } from "./VehicleCostTabs";
import Modal from "@/components/ui/Modal";

type Tab = "list" | "period" | "expense" | "summary";
const TABS: Array<[Tab, string]> = [["list", "차량"], ["period", "기간 비용"], ["expense", "지출 내역"], ["summary", "비용 요약"]];
const TAB_KEY = "ll.vehicles.tab";

export default function VehiclesPage() {
  const isAdmin = Boolean(useMe()?.is_admin);
  const [tab, setTab] = useState<Tab>(() => {
    const v = localStorage.getItem(TAB_KEY);
    return TABS.some(([k]) => k === v) ? (v as Tab) : "list";
  });
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [managers, setManagers] = useState<ManagerRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function reload() {
    const [v, m] = await Promise.allSettled([api.listVehicles(), api.listManagers()]);
    if (v.status === "fulfilled") { setVehicles(v.value.items); setError(""); } else setError(errText(v.reason));
    if (m.status === "fulfilled") setManagers(m.value.items);
    setLoading(false);
  }

  useEffect(() => { reload().catch(() => {}); }, []);
  useEffect(() => {
    try { localStorage.setItem(TAB_KEY, tab); } catch { /* 무시 */ }
  }, [tab]);

  return (
    <PageLayout
      title="차량·지출"
      right={
        <div className="seg">
          {TABS.map(([k, label]) => (
            <button key={k} type="button" className={tab === k ? "on" : undefined} onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>
      }
    >
      {error && <div className="mt"><ErrorBox message={error} /></div>}
      {loading ? (
        <Spinner />
      ) : (
        <>
          {tab === "list" && <VehicleListTab vehicles={vehicles} managers={managers} isAdmin={isAdmin} onChanged={reload} />}
          {tab === "period" && <PeriodCostTab vehicles={vehicles} isAdmin={isAdmin} />}
          {tab === "expense" && <ExpenseTab vehicles={vehicles} isAdmin={isAdmin} />}
          {tab === "summary" && <CostSummaryTab />}
        </>
      )}
    </PageLayout>
  );
}

type VForm = { plate_no: string; model: string; fuel_type: FuelType; eff: string; pdate: string; price: string; memo: string; active: boolean };
const EMPTY: VForm = { plate_no: "", model: "", fuel_type: "diesel", eff: "", pdate: "", price: "", memo: "", active: true };

function VehicleListTab({ vehicles, managers, isAdmin, onChanged }: {
  vehicles: Vehicle[]; managers: ManagerRow[]; isAdmin: boolean; onChanged: () => Promise<void>;
}) {
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [f, setF] = useState<VForm>(EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const mgrName = useMemo(() => new Map(managers.map((m) => [m.manager_id, m.name ?? `#${m.manager_id}`])), [managers]);
  const set = <K extends keyof VForm>(k: K, v: VForm[K]) => setF((p) => ({ ...p, [k]: v }));

  function open(v?: Vehicle) {
    setError("");
    setEditing(v ? v.id : "new");
    setF(v ? {
      plate_no: v.plate_no, model: v.model ?? "", fuel_type: v.fuel_type,
      eff: v.fuel_efficiency != null ? String(v.fuel_efficiency) : "", pdate: v.purchase_date ?? "",
      price: v.purchase_price != null ? String(v.purchase_price) : "", memo: v.memo ?? "", active: v.active,
    } : EMPTY);
  }

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try { await fn(); await onChanged(); } catch (e) { setError(errText(e)); } finally { setBusy(false); }
  }

  function save() {
    const eff = f.eff.trim() ? Number(f.eff) : null;
    const price = f.price.trim() ? parseAmount(f.price) : null;
    if (!f.plate_no.trim()) return setError("차량번호를 입력하세요");
    if (eff !== null && !(eff > 0)) return setError("연비는 0보다 큰 숫자로 입력하세요");
    if (price !== null && Number.isNaN(price)) return setError("구매가는 숫자로 입력하세요");
    const body: VehicleInput = {
      plate_no: f.plate_no.trim(), model: f.model.trim() || null, fuel_type: f.fuel_type,
      fuel_efficiency: eff, purchase_date: f.pdate || null, purchase_price: price,
      memo: f.memo.trim() || null, active: f.active,
    };
    run(async () => {
      if (editing === "new") await api.createVehicle(body);
      else if (editing != null) await api.updateVehicle(editing, body);
      setEditing(null);
    });
  }

  function remove(v: Vehicle) {
    if (!window.confirm(`${v.plate_no} 차량을 삭제할까요?\n목록에서 사라지지만 과거 비용·지출 기록은 유지됩니다.`)) return;
    run(() => api.deleteVehicle(v.id));
  }

  return (
    <>
      <Panel title={`차량 ${vehicles.length}대`} right={isAdmin && <Button size="sm" variant="primary" onClick={() => open()}>차량 추가</Button>}>
        {error && !editing && <div className="stack"><ErrorBox message={error} /></div>}
        {vehicles.length === 0 ? (
          <div className="muted small">등록된 차량이 없습니다.</div>
        ) : (
          <DataTable columns={["차량번호", "차종", "연료", { label: "공인연비", num: true }, "구매일", { label: "구매가", num: true }, "현재 배정", "상태", ...(isAdmin ? ["관리"] : [])]}>
            {vehicles.map((v) => (
              <tr key={v.id} className={v.active ? undefined : "off"}>
                <td>{v.plate_no}</td>
                <td>{v.model ?? "-"}</td>
                <td>{FUEL_LABEL[v.fuel_type]}</td>
                <td className="num">{v.fuel_efficiency != null ? `${v.fuel_efficiency}${v.fuel_type === "ev" ? "km/kWh" : "km/L"}` : "-"}</td>
                <td>{v.purchase_date ?? "-"}</td>
                <td className="num">{v.purchase_price != null ? won(v.purchase_price) : "-"}</td>
                <td>{v.manager_ids.length ? v.manager_ids.map((id) => mgrName.get(id) ?? `#${id}`).join(", ") : <span className="muted">-</span>}</td>
                <td>{v.active ? <Chip tone="ok">사용</Chip> : <Chip>중지</Chip>}</td>
                {isAdmin && (
                  <td>
                    <div className="row-actions">
                      <Button size="sm" onClick={() => open(v)}>편집</Button>
                      <Button size="sm" variant="danger" disabled={busy} onClick={() => remove(v)}>삭제</Button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>

      <Modal
        open={isAdmin && editing != null}
        title={editing === "new" ? "차량 추가" : "차량 수정"}
        onClose={() => setEditing(null)}
        footer={
          <>
            <Button onClick={() => setEditing(null)}>취소</Button>
            <Button variant="primary" disabled={busy} onClick={save}>저장</Button>
          </>
        }
      >
        {error && <div className="stack"><ErrorBox message={error} /></div>}
        <div className="form-grid">
          <label className="field">차량번호 *<input className="input" value={f.plate_no} maxLength={20} onChange={(e) => set("plate_no", e.target.value)} placeholder="12가 3456" /></label>
          <label className="field">차종<input className="input" value={f.model} maxLength={100} onChange={(e) => set("model", e.target.value)} placeholder="포터2" /></label>
          <label className="field">연료
            <select className="input" value={f.fuel_type} onChange={(e) => set("fuel_type", e.target.value as FuelType)}>
              {(Object.keys(FUEL_LABEL) as FuelType[]).map((k) => <option key={k} value={k}>{FUEL_LABEL[k]}</option>)}
            </select>
          </label>
          <label className="field">공인연비 ({f.fuel_type === "ev" ? "km/kWh" : "km/L"})<input className="input" inputMode="decimal" value={f.eff} onChange={(e) => set("eff", e.target.value)} placeholder="9.5" /></label>
          <label className="field">구매일<input type="date" className="input" value={f.pdate} onChange={(e) => set("pdate", e.target.value)} /></label>
          <label className="field">구매가(원)<input className="input" inputMode="numeric" value={f.price} onChange={(e) => set("price", e.target.value)} /></label>
          <label className="field">상태
            <select className="input" value={f.active ? "1" : "0"} onChange={(e) => set("active", e.target.value === "1")}>
              <option value="1">사용</option><option value="0">중지</option>
            </select>
          </label>
          <label className="field field-wide">메모<input className="input" value={f.memo} maxLength={500} onChange={(e) => set("memo", e.target.value)} /></label>
        </div>
      </Modal>
    </>
  );
}
