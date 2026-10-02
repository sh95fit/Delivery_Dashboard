import { useCallback, useEffect, useMemo, useState } from "react";
import Panel from "../../components/ui/Panel";
import Button from "../../components/ui/Button";
import DataTable from "../../components/ui/DataTable";
import * as api from "../../api/masters";
import { PERIOD_CATS, EXPENSE_CATS } from "../../api/masters";
import type { Vehicle, PeriodCost, Expense, CostSummary } from "../../api/masters";
import { won, todayKst } from "../../lib/format";
import { errText, parseAmount, daysIncl, yearEnd } from "../../lib/form";


type Vid = number | "";
type Props = { vehicles: Vehicle[]; isAdmin: boolean };


const thisMonth = () => todayKst().slice(0, 7);

function monthBounds(ym: string) {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return { from: `${ym}-01`, to: `${ym}-${String(last).padStart(2, "0")}` };
}

/* 실행 → 실패 시 에러 표시 → 성공 시 목록 다시 불러오기 */
function useRunner(reload: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await reload();
      return true;
    } catch (e) {
      setError(errText(e));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, setError, run };
}

function VehicleSelect({
  vehicles, value, onChange, all,
}: { vehicles: Vehicle[]; value: Vid; onChange: (v: Vid) => void; all?: boolean }) {
  return (
    <select
      className="input"
      value={value}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}
    >
      <option value="">{all ? "전체 차량" : "차량 선택"}</option>
      {vehicles.map((v) => (
        <option key={v.id} value={v.id}>{v.plate_no}</option>
      ))}
    </select>
  );
}

function ErrorLine({ error }: { error: string | null }) {
  return error ? <p className="form-error">{error}</p> : null;
}

/* ───────── 기간 비용 ───────── */
export function PeriodCostTab({ vehicles, isAdmin }: Props) {
  const [filter, setFilter] = useState<Vid>("");
  const [items, setItems] = useState<PeriodCost[] | null>(null);

  const load = useCallback(async () => {
    const res = await api.listPeriodCosts(filter === "" ? undefined : filter);
    setItems(res.items);
  }, [filter]);
  const { busy, error, setError, run } = useRunner(load);

  useEffect(() => {
    load().catch((e) => setError(errText(e)));
  }, [load, setError]);

  const [vid, setVid] = useState<Vid>("");
  const [cat, setCat] = useState("insurance");
  const [start, setStart] = useState(todayKst());
  const [end, setEnd] = useState(yearEnd(todayKst()));
  const [amount, setAmount] = useState("");
  const [memo, setMemo] = useState("");

  const amt = parseAmount(amount);
  const days = start && end && start <= end ? daysIncl(start, end) : 0;

  const add = async () => {
    if (vid === "") return setError("차량을 선택하세요.");
    if (!amt || amt <= 0) return setError("금액을 확인하세요.");
    if (!days) return setError("기간을 확인하세요. 종료일이 시작일보다 빠릅니다.");
    const ok = await run(() =>
      api.addPeriodCost({
        vehicle_id: vid, category: cat, start_date: start, end_date: end,
        amount: amt, memo: memo || null,
      }),
    );
    if (ok) { setAmount(""); setMemo(""); }
  };

  return (
    <>
      <Panel
        title="기간 비용"
        right={<VehicleSelect vehicles={vehicles} value={filter} onChange={setFilter} all />}
      >
        <ErrorLine error={error} />
        {!items ? (
          <p className="muted">불러오는 중…</p>
        ) : items.length === 0 ? (
          <p className="muted">등록된 기간 비용이 없습니다.</p>
        ) : (
          <DataTable
            columns={[
              "차량", "항목", "기간", { label: "일수", num: true },
              { label: "금액", num: true }, { label: "일 환산", num: true }, "메모",
              ...(isAdmin ? ["관리"] : []),
            ]}
          >
            {items.map((r) => {
              const d = daysIncl(r.start_date, r.end_date);
              return (
                <tr key={r.id}>
                  <td>{r.plate_no ?? `#${r.vehicle_id}`}</td>
                  <td>{PERIOD_CATS[r.category] ?? r.category}</td>
                  <td>{r.start_date} ~ {r.end_date}</td>
                  <td className="num">{d}일</td>
                  <td className="num">{won(r.amount)}</td>
                  <td className="num">{won(Math.floor(r.amount / d))}</td>
                  <td>{r.memo ?? ""}</td>
                  {isAdmin && (
                    <td>
                      <Button
                        size="sm" variant="danger" disabled={busy}
                        onClick={() =>
                          window.confirm("이 기간 비용을 삭제할까요?") &&
                          run(() => api.deletePeriodCost(r.id))
                        }
                      >
                        삭제
                      </Button>
                    </td>
                  )}
                </tr>
              );
            })}
          </DataTable>
        )}
      </Panel>

      {isAdmin && (
        <Panel title="기간 비용 추가" desc="보험·리스처럼 기간 단위로 내는 비용은 일 단위로 나눠 집계됩니다.">
          <div className="form-grid">
            <label className="field">차량
              <VehicleSelect vehicles={vehicles} value={vid} onChange={setVid} />
            </label>
            <label className="field">항목
              <select className="input" value={cat} onChange={(e) => setCat(e.target.value)}>
                {Object.entries(PERIOD_CATS).map(([k, l]) => (
                  <option key={k} value={k}>{l}</option>
                ))}
              </select>
            </label>
            <label className="field">시작일
              <input type="date" className="input" value={start}
                onChange={(e) => { setStart(e.target.value); setEnd(yearEnd(e.target.value)); }} />
            </label>
            <label className="field">종료일
              <input type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
            <label className="field">금액(원)
              <input className="input" inputMode="numeric" value={amount}
                onChange={(e) => setAmount(e.target.value)} />
            </label>
            <label className="field field-wide">메모
              <input className="input" value={memo} maxLength={200}
                onChange={(e) => setMemo(e.target.value)} />
            </label>
            <div className="form-actions">
              {amt && days ? (
                <span className="muted">{days}일 · 일 {won(Math.floor(amt / days))}</span>
              ) : null}
              <Button variant="primary" disabled={busy} onClick={add}>추가</Button>
            </div>
          </div>
        </Panel>
      )}
    </>
  );
}

/* ───────── 지출 내역 ───────── */
export function ExpenseTab({ vehicles, isAdmin }: Props) {
  const [month, setMonth] = useState(thisMonth());
  const [filter, setFilter] = useState<Vid>("");
  const [items, setItems] = useState<Expense[] | null>(null);

  const load = useCallback(async () => {
    const { from, to } = monthBounds(month);
    const res = await api.listExpenses(from, to, filter === "" ? undefined : filter);
    setItems(res.items);
  }, [month, filter]);
  const { busy, error, setError, run } = useRunner(load);

  useEffect(() => {
    load().catch((e) => setError(errText(e)));
  }, [load, setError]);

  const total = useMemo(() => (items ?? []).reduce((s, r) => s + r.amount, 0), [items]);

  const [vid, setVid] = useState<Vid>("");
  const [date, setDate] = useState(todayKst());
  const [cat, setCat] = useState("repair");
  const [amount, setAmount] = useState("");
  const [memo, setMemo] = useState("");

  const add = async () => {
    const amt = parseAmount(amount);
    if (vid === "") return setError("차량을 선택하세요.");
    if (!amt || amt <= 0) return setError("금액을 확인하세요.");
    const ok = await run(() =>
      api.addExpense({
        vehicle_id: vid, expense_date: date, category: cat,
        amount: amt, memo: memo || null,
      }),
    );
    if (ok) { setAmount(""); setMemo(""); }
  };

  return (
    <>
      <Panel
        title="지출 내역"
        right={
          <div className="row-gap">
            <input type="month" className="input" value={month} onChange={(e) => setMonth(e.target.value)} />
            <VehicleSelect vehicles={vehicles} value={filter} onChange={setFilter} all />
          </div>
        }
      >
        <ErrorLine error={error} />
        {!items ? (
          <p className="muted">불러오는 중…</p>
        ) : items.length === 0 ? (
          <p className="muted">이 달 지출 내역이 없습니다.</p>
        ) : (
          <DataTable
            columns={[
              "일자", "차량", "항목", { label: "금액", num: true }, "메모", "입력자",
              ...(isAdmin ? ["관리"] : []),
            ]}
          >
            {items.map((r) => (
              <tr key={r.id}>
                <td>{r.expense_date}</td>
                <td>{r.plate_no ?? `#${r.vehicle_id}`}</td>
                <td>{EXPENSE_CATS[r.category] ?? r.category}</td>
                <td className="num">{won(r.amount)}</td>
                <td>{r.memo ?? ""}</td>
                <td>{r.created_by ?? "-"}</td>
                {isAdmin && (
                  <td>
                    <Button
                      size="sm" variant="danger" disabled={busy}
                      onClick={() =>
                        window.confirm("이 지출을 삭제할까요?") &&
                        run(() => api.deleteExpense(r.id))
                      }
                    >
                      삭제
                    </Button>
                  </td>
                )}
              </tr>
            ))}
            <tr className="sum">
              <td colSpan={3}>합계</td>
              <td className="num">{won(total)}</td>
              <td colSpan={isAdmin ? 3 : 2} />
            </tr>
          </DataTable>
        )}
      </Panel>

      {isAdmin && (
        <Panel title="지출 추가">
          <div className="form-grid">
            <label className="field">차량
              <VehicleSelect vehicles={vehicles} value={vid} onChange={setVid} />
            </label>
            <label className="field">일자
              <input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
            <label className="field">항목
              <select className="input" value={cat} onChange={(e) => setCat(e.target.value)}>
                {Object.entries(EXPENSE_CATS).map(([k, l]) => (
                  <option key={k} value={k}>{l}</option>
                ))}
              </select>
            </label>
            <label className="field">금액(원)
              <input className="input" inputMode="numeric" value={amount}
                onChange={(e) => setAmount(e.target.value)} />
            </label>
            <label className="field field-wide">메모
              <input className="input" value={memo} maxLength={200}
                onChange={(e) => setMemo(e.target.value)} />
            </label>
            <div className="form-actions">
              <Button variant="primary" disabled={busy} onClick={add}>추가</Button>
            </div>
          </div>
        </Panel>
      )}
    </>
  );
}

/* ───────── 비용 요약 ───────── */
type SummaryRow = CostSummary["vehicles"][number];

export function CostSummaryTab() {
  const [month, setMonth] = useState(thisMonth());
  const [withExp, setWithExp] = useState(true);
  const [data, setData] = useState<CostSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const { from, to } = monthBounds(month);
    setData(null);
    setError(null);
    api.getCostSummary(from, to).then(setData).catch((e) => setError(errText(e)));
  }, [month]);

  const rowTotal = (r: SummaryRow) => r.period_cost + (withExp ? r.expense : 0);
  const totals = data?.totals;
  const grand = totals ? totals.period_cost + (withExp ? totals.expense : 0) : 0;

  return (
    <Panel
      title="비용 요약"
      desc="기간 비용은 해당 월에 걸친 일수만큼만, 지출은 일자 기준으로 합산합니다."
      right={
        <div className="row-gap">
          <input type="month" className="input" value={month} onChange={(e) => setMonth(e.target.value)} />
          <label className="check">
            <input type="checkbox" checked={withExp} onChange={(e) => setWithExp(e.target.checked)} />
            지출 포함
          </label>
        </div>
      }
    >
      <ErrorLine error={error} />
      {!data ? (
        !error && <p className="muted">불러오는 중…</p>
      ) : data.vehicles.length === 0 ? (
        <p className="muted">이 달 비용이 없습니다.</p>
      ) : (
        <DataTable
          columns={[
            "차량",
            { label: "기간 비용", num: true },
            ...(withExp ? [{ label: "지출", num: true }] : []),
            { label: "합계", num: true },
          ]}
        >
          {data.vehicles.map((r) => (
            <tr key={r.vehicle_id}>
              <td>{r.plate_no ?? `#${r.vehicle_id}`}</td>
              <td className="num">{won(r.period_cost)}</td>
              {withExp && <td className="num">{won(r.expense)}</td>}
              <td className="num">{won(rowTotal(r))}</td>
            </tr>
          ))}
          <tr className="sum">
            <td>합계 ({data.days}일)</td>
            <td className="num">{won(data.totals.period_cost)}</td>
            {withExp && <td className="num">{won(data.totals.expense)}</td>}
            <td className="num">{won(grand)}</td>
          </tr>
        </DataTable>
      )}
    </Panel>
  );
}
