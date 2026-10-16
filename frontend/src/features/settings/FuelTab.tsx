import { useCallback, useEffect, useMemo, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Modal from "@/components/ui/Modal";
import * as fuel from "@/api/fuel";
import type { FuelImportRecord, FuelLog, FuelSummary } from "@/api/fuel";
import { FUEL_LABEL } from "@/api/masters";
import type { ManagerRow, Vehicle } from "@/api/masters";
import { errText, parseAmount } from "@/lib/form";
import { kstDateTime, todayKst, won } from "@/lib/format";
import FuelImport from "./FuelImport";

/* S3-P1b-2b 유류비 탭 — 주유 기록 입력·월 집계(차량·매니저·일자)·월 마감 */

type Props = { vehicles: Vehicle[]; managers: ManagerRow[]; isAdmin: boolean };
type Form = { vid: string; date: string; total: string; supply: string; vat: string; qty: string; station: string; memo: string };

const thisMonth = () => todayKst().slice(0, 7);
const supplyOf = (total: number) => Math.floor((total * 10 + 5) / 11); // 서버 supply_of와 같은 반올림
const optAmount = (s: string) => (s.trim() ? parseAmount(s) : null);
const qtyText = (q: number | null, unit = "") =>
  q == null ? "-" : `${q.toLocaleString("ko-KR", { maximumFractionDigits: 3 })}${unit}`;

export default function FuelTab({ vehicles, managers, isAdmin }: Props) {
  const [month, setMonth] = useState(thisMonth());
  const [filter, setFilter] = useState("");
  const [sum, setSum] = useState<FuelSummary | null>(null);
  const [logs, setLogs] = useState<FuelLog[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const [imports, setImports] = useState<FuelImportRecord[]>([]);
  const [f, setF] = useState<Form>({ vid: "", date: todayKst(), total: "", supply: "", vat: "", qty: "", station: "", memo: "" });

  const load = useCallback(async () => {
    const [s, l, im] = await Promise.all([
      fuel.getFuelSummary(month),
      fuel.listFuelLogs(month, filter ? Number(filter) : undefined),
      fuel.listFuelImports(month),
    ]);
    setSum(s);
    setLogs(l.items);
    setImports(im);
  }, [month, filter]);

  useEffect(() => {
    setError("");
    load().catch((e) => setError(errText(e)));
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try { await fn(); await load(); return true; } catch (e) { setError(errText(e)); return false; } finally { setBusy(false); }
  }

  const vById = useMemo(() => new Map(vehicles.map((v) => [v.id, v])), [vehicles]);
  const mgrName = useMemo(() => new Map(managers.map((m) => [m.manager_id, m.name ?? `#${m.manager_id}`])), [managers]);
  const closed = sum?.closed ?? null;
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));

  // 입력 창 미리보기 (서버 계산과 같은 규칙)
  const sel = f.vid ? vById.get(Number(f.vid)) : undefined;
  const total = parseAmount(f.total);
  const sIn = optAmount(f.supply);
  const vIn = optAmount(f.vat);
  let pv: { s: number; v: number } | null = null;
  if (total > 0) {
    if (sIn == null && vIn == null) pv = { s: supplyOf(total), v: total - supplyOf(total) };
    else if (vIn == null && sIn != null) pv = { s: sIn, v: total - sIn };
    else if (sIn == null && vIn != null) pv = { s: total - vIn, v: vIn };
    else if (sIn != null && vIn != null) pv = { s: sIn, v: vIn };
  }

  function openAdd() {
    const today = todayKst();
    setError("");
    setF({ vid: "", date: today.startsWith(month) ? today : `${month}-01`, total: "", supply: "", vat: "", qty: "", station: "", memo: "" });
    setAdding(true);
  }

  async function save() {
    if (!sel) return setError("차량을 선택하세요");
    if (!(total > 0)) return setError("합계 금액을 확인하세요");
    if ([sIn, vIn].some((x) => x != null && Number.isNaN(x))) return setError("공급가액·부가세는 숫자로 입력하세요");
    const qty = f.qty.trim() ? Number(f.qty) : null;
    if (qty !== null && !(qty > 0)) return setError("수량은 0보다 큰 숫자로 입력하세요");
    const vehicleId = sel.id;
    const ok = await run(() => fuel.addFuelLog({
      vehicle_id: vehicleId, fuel_date: f.date, total_amount: total,
      supply_amount: sIn, vat_amount: vIn, quantity: qty,
      unit_price: qty ? Math.round((total / qty) * 100) / 100 : null,
      station: f.station.trim() || null, memo: f.memo.trim() || null,
    }));
    if (ok) setAdding(false);
  }

  function remove(r: FuelLog) {
    if (!window.confirm(`${r.fuel_date} ${r.plate_no ?? ""} ${won(r.total_amount)} 주유 기록을 삭제할까요?`)) return;
    run(() => fuel.deleteFuelLog(r.id));
  }

  function closeMonth() {
    if (!sum) return;
    const msg = `${month} 유류비를 마감할까요?\n주유 ${sum.totals.count}건 · 비용 ${won(sum.totals.cost)}\n`
      + "마감하면 이 달 기록은 추가·삭제할 수 없고, 물류비에 확정 금액으로 반영됩니다.";
    if (!window.confirm(msg)) return;
    run(() => fuel.closeFuelMonth(month, null));
  }

  function releaseMonth() {
    const reason = window.prompt(`${month} 유류비 마감을 해제합니다. 해제 사유를 입력하세요 (필수)`);
    if (reason == null) return;
    if (!reason.trim()) return setError("해제 사유를 입력하세요");
    run(() => fuel.releaseFuelMonth(month, reason.trim()));
  }


  function undoImport(im: FuelImportRecord) {
    const reason = window.prompt(
      `업로드 #${im.id} (${im.file_name ?? "파일"} · ${im.active_count}건 · ${won(im.total_amount)})을 되돌립니다.\n`
      + "이 업로드로 저장된 주유 기록이 모두 삭제됩니다(다른 달 포함). 사유를 입력하세요 (필수)");
    if (reason == null) return;
    if (!reason.trim()) return setError("되돌리기 사유를 입력하세요");
    run(() => fuel.undoFuelImport(im.id, reason.trim()));
  }

  function exportMonth() {
    run(() => fuel.exportFuelMonth(month));
  }


  const unit = (ft: string) => (ft === "ev" ? "kWh" : "L");

  return (
    <>
      <Panel
        title="유류비"
        right={
          <div className="row-gap">
            <input type="month" className="input" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
            {sum && (closed ? <Chip tone="ok">마감 · 확정</Chip> : <Chip tone="warn">미마감 · 예상</Chip>)}
            {isAdmin && !closed && <Button size="sm" variant="primary" onClick={openAdd}>주유 입력</Button>}
            {isAdmin && <Button size="sm" disabled={busy} onClick={() => { setError(""); setImporting(true); }}>엑셀 업로드</Button>}
            <Button size="sm" disabled={busy || !sum?.totals.count} onClick={exportMonth}>엑셀 내보내기</Button>
            {isAdmin && !closed && <Button size="sm" disabled={busy || !sum?.totals.count} onClick={closeMonth}>월 마감</Button>}
            {isAdmin && closed && <Button size="sm" variant="danger" disabled={busy} onClick={releaseMonth}>마감 해제</Button>}
          </div>
        }
      >
        {error && !adding && <div className="stack"><ErrorBox message={error} /></div>}
        <p className="muted small">
          비용 = 부가세 공제 차량은 공급가액, 불공제 차량은 합계. 한 달 비용을 그달 영업일({sum?.open_days ?? "-"}일)로 나눠
          그날 차량에 배정된 매니저에게 반영합니다. 마감 전에는 지금까지 입력한 기록으로 예상하고, 마감하면 확정됩니다.
          월 마감은 그달이 끝난 다음 날부터 할 수 있습니다.
        </p>
        {closed && (
          <p className="muted small">
            마감 {closed.closed_at?.slice(0, 10) ?? ""} · {closed.closed_by ?? ""} · {closed.log_count}건 · 비용 {won(closed.cost_amount)}
          </p>
        )}
        {!sum ? (
          <p className="muted">불러오는 중…</p>
        ) : (
          <DataTable columns={[
            { label: "주유 건수", num: true }, { label: "수량(L·kWh)", num: true }, { label: "합계", num: true },
            { label: "공급가액", num: true }, { label: "부가세", num: true }, { label: "비용(물류비 반영)", num: true },
            { label: "영업일당", num: true },
          ]}>
            <tr>
              <td className="num">{sum.totals.count}건</td>
              <td className="num">{qtyText(sum.totals.quantity)}</td>
              <td className="num">{won(sum.totals.total)}</td>
              <td className="num">{won(sum.totals.supply)}</td>
              <td className="num">{won(sum.totals.vat)}</td>
              <td className="num"><b>{won(sum.totals.cost)}</b></td>
              <td className="num">{sum.open_days ? won(Math.floor(sum.totals.cost / sum.open_days)) : "-"}</td>
            </tr>
          </DataTable>
        )}
      </Panel>

      {sum && sum.totals.count > 0 && (
        <>
          <Panel title="차량별">
            <DataTable columns={["차량", "연료", "부가세", { label: "건수", num: true }, { label: "수량", num: true },
              { label: "합계", num: true }, { label: "비용", num: true }]}>
              {sum.vehicles.map((v) => (
                <tr key={v.vehicle_id}>
                  <td>{v.plate_no ?? `#${v.vehicle_id}`}</td>
                  <td>{FUEL_LABEL[v.fuel_type]}</td>
                  <td>{v.vat_deductible ? <Chip tone="internal">공제 · 공급가액</Chip> : <Chip>불공제 · 합계</Chip>}</td>
                  <td className="num">{v.count}건</td>
                  <td className="num">{qtyText(v.quantity, unit(v.fuel_type))}</td>
                  <td className="num">{won(v.total)}</td>
                  <td className="num">{won(v.cost)}</td>
                </tr>
              ))}
            </DataTable>
          </Panel>

          <Panel title="매니저별 (영업일 배분 후 그날 차량 배정 기준)">
            <DataTable columns={["매니저", "차량", { label: "비용", num: true }]}>
              {sum.managers.map((m) => (
                <tr key={m.manager_id ?? "none"}>
                  <td>{m.manager_id == null ? <span className="muted">계정 미지정</span> : mgrName.get(m.manager_id) ?? `#${m.manager_id}`}</td>
                  <td>{m.vehicle_ids.map((id) => vById.get(id)?.plate_no ?? `#${id}`).join(", ")}</td>
                  <td className="num">{won(m.cost)}</td>
                </tr>
              ))}
            </DataTable>
          </Panel>

          <Panel title="일자별 (주유한 날 기준)">
            <DataTable columns={["일자", { label: "건수", num: true }, { label: "수량", num: true },
              { label: "합계", num: true }, { label: "비용", num: true }]}>
              {sum.days.map((d) => (
                <tr key={d.date}>
                  <td>{d.date}</td>
                  <td className="num">{d.count}건</td>
                  <td className="num">{qtyText(d.quantity)}</td>
                  <td className="num">{won(d.total)}</td>
                  <td className="num">{won(d.cost)}</td>
                </tr>
              ))}
            </DataTable>
          </Panel>
        </>
      )}

      <Panel
        title={`주유 기록${logs ? ` ${logs.length}건` : ""}`}
        right={
          <select className="input" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">전체 차량</option>
            {vehicles.map((v) => <option key={v.id} value={v.id}>{v.plate_no}</option>)}
          </select>
        }
      >
        {!logs ? (
          <p className="muted">불러오는 중…</p>
        ) : logs.length === 0 ? (
          <p className="muted">이 달 주유 기록이 없습니다.</p>
        ) : (
          <DataTable columns={["일자", "차량", "연료", { label: "수량", num: true }, { label: "단가", num: true },
            { label: "합계", num: true }, { label: "공급가액", num: true }, { label: "부가세", num: true },
            { label: "비용", num: true }, "주유소", "메모", "입력", ...(isAdmin && !closed ? ["관리"] : [])]}>
            {logs.map((r) => (
              <tr key={r.id}>
                <td>{r.fuel_date}</td>
                <td>{r.plate_no ?? `#${r.vehicle_id}`}</td>
                <td>{FUEL_LABEL[r.fuel_type]}</td>
                <td className="num">{qtyText(r.quantity, unit(r.fuel_type))}</td>
                <td className="num">{r.unit_price != null ? won(Math.round(r.unit_price)) : "-"}</td>
                <td className="num">{won(r.total_amount)}</td>
                <td className="num">{won(r.supply_amount)}</td>
                <td className="num">{won(r.vat_amount)}</td>
                <td className="num">{won(r.cost)}</td>
                <td>{r.station ?? ""}</td>
                <td>{r.memo ?? ""}</td>
                <td>{r.source === "excel" ? <Chip>엑셀</Chip> : <Chip>직접</Chip>}</td>
                {isAdmin && !closed && (
                  <td><Button size="sm" variant="danger" disabled={busy} onClick={() => remove(r)}>삭제</Button></td>
                )}
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>

      {imports.length > 0 && (
        <Panel title={`엑셀 업로드 기록 ${imports.length}건`}>
          <DataTable columns={["#", "파일", "기간", { label: "남은/저장", num: true }, { label: "합계", num: true },
            "올린 사람", "상태", ...(isAdmin ? ["관리"] : [])]}>
            {imports.map((im) => (
              <tr key={im.id} className={im.undone_at ? "off" : undefined}>
                <td>{im.id}</td>
                <td>{im.file_name ?? "-"}</td>
                <td>{im.date_from} ~ {im.date_to}</td>
                <td className="num">{im.active_count}/{im.log_count}건</td>
                <td className="num">{won(im.total_amount)}</td>
                <td>{im.created_by ?? "-"} · {kstDateTime(im.created_at)}</td>
                <td>
                  {im.undone_at
                    ? <Chip title={im.undo_reason ?? ""}>되돌림 · {kstDateTime(im.undone_at)} · {im.undo_reason ?? ""}</Chip>
                    : <Chip tone="ok">반영</Chip>}
                </td>
                {isAdmin && (
                  <td>
                    {!im.undone_at && (
                      <Button size="sm" variant="danger" disabled={busy} onClick={() => undoImport(im)}>되돌리기</Button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </DataTable>
        </Panel>
      )}

      <Modal
        open={isAdmin && adding}
        title="주유 입력"
        onClose={() => setAdding(false)}
        footer={
          <>
            {pv && sel ? (
              <span className="muted small grow">
                공급가액 {won(pv.s)} · 부가세 {won(pv.v)} → 물류비 {won(sel.vat_deductible ? pv.s : total)}
                ({sel.vat_deductible ? "공제 · 공급가액" : "불공제 · 합계"})
              </span>
            ) : null}
            <Button onClick={() => setAdding(false)}>취소</Button>
            <Button variant="primary" disabled={busy} onClick={save}>저장</Button>
          </>
        }
      >
        {error && <div className="stack"><ErrorBox message={error} /></div>}
        <p className="muted small">공급가액·부가세를 비우면 합계 ÷ 1.1로 자동 계산합니다. 영수증에 적힌 값이 있으면 그대로 입력하세요.</p>
        <div className="form-grid">
          <label className="field">차량 *
            <select className="input" value={f.vid} onChange={(e) => set("vid", e.target.value)}>
              <option value="">차량 선택</option>
              {vehicles.filter((v) => v.active).map((v) => (
                <option key={v.id} value={v.id}>{v.plate_no} · {FUEL_LABEL[v.fuel_type]}</option>
              ))}
            </select>
          </label>
          <label className="field">주유일 *
            <input type="date" className="input" value={f.date} max={todayKst()} onChange={(e) => set("date", e.target.value)} />
          </label>
          <label className="field">합계(원) *
            <input className="input" inputMode="numeric" value={f.total} onChange={(e) => set("total", e.target.value)} placeholder="144000" />
          </label>
          <label className="field">수량 ({sel?.fuel_type === "ev" ? "kWh" : "L"})
            <input className="input" inputMode="decimal" value={f.qty} onChange={(e) => set("qty", e.target.value)} placeholder="77.5" />
          </label>
          <label className="field">공급가액(원)
            <input className="input" inputMode="numeric" value={f.supply} onChange={(e) => set("supply", e.target.value)} placeholder="비우면 자동" />
          </label>
          <label className="field">부가세(원)
            <input className="input" inputMode="numeric" value={f.vat} onChange={(e) => set("vat", e.target.value)} placeholder="비우면 자동" />
          </label>
          <label className="field">주유소
            <input className="input" value={f.station} maxLength={100} onChange={(e) => set("station", e.target.value)} />
          </label>
          <label className="field">메모
            <input className="input" value={f.memo} maxLength={200} onChange={(e) => set("memo", e.target.value)} />
          </label>
        </div>
      </Modal>
      {isAdmin && importing && (
        <FuelImport
          onClose={() => setImporting(false)}
          onDone={async (m) => { if (m && m !== month) setMonth(m); else await load(); }}
        />
      )}
    </>
  );
}
