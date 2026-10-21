import { useEffect, useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { useMe } from "@/layouts/shell";
import * as api from "@/api/logistics";
import type { CostRow, CostView } from "@/api/logistics";
import { daysIncl, errText } from "@/lib/form";
import { monthRange, num, todayKst, won } from "@/lib/format";

/* S3-P2a 물류비 — 매출(부가세 제외) 대비 인건비·인센티브·차량비·유류비. 지급 금액 아님 */
type Mode = "month" | "range";
const WD = ["일", "월", "화", "수", "목", "금", "토"];
const MAX_DAYS = 366;

const COLUMNS = [
  { label: "순매출", num: true },
  ...api.COST_COLS.map(([, label]) => ({ label, num: true })),
  { label: "물류비 합계", num: true },
  { label: "이익", num: true },
  { label: "비용률", num: true },
  { label: "주행 km", num: true },
  { label: "주행 시간", num: true },  
  { label: "NCP 예상 유류비", num: true },
  { label: "오피넷 기준", num: true },
];

const ratio = (r: CostRow) => (r.cost_ratio == null ? "-" : `${r.cost_ratio}%`);
const hm = (min?: number) => (min ? `${Math.floor(min / 60)}:${String(min % 60).padStart(2, "0")}` : "-");   // 분 → 시:분

function Cells({ r }: { r: CostRow }) {
  return (
    <>
      <td className="num">{num(r.net_revenue)}</td>
      {api.COST_COLS.map(([k]) => <td key={k} className="num">{num(r[k])}</td>)}
      <td className="num"><b>{num(r.cost_total)}</b></td>
      <td className="num">{num(r.profit)}</td>
      <td className="num">{ratio(r)}</td>
      <td className="num muted">{r.route_km ? r.route_km.toLocaleString("ko-KR") : "-"}</td>
      <td className="num muted">{hm(r.route_min)}</td>      
      <td className="num muted">{r.ncp_fuel ? num(r.ncp_fuel) : "-"}</td>
      <td className="num muted">{r.calc_fuel ? num(r.calc_fuel) : "-"}</td>
    </>
  );
}

/* [S3-P2e] 유류비 카드: 마감 전 = NCP 예상, 기간 전체 마감 = 확정 유류비, 일부 마감 = 확정 + 미마감 주유 기록 */
function fuelCard(view: CostView) {
  const t = view.totals;
  const open = t.fuel_est > 0 || view.issues.some((i) => i.msg.includes("유류비 미마감"));
  const ref = `NCP 예상 ${won(t.ncp_fuel)} · 오피넷 기준 ${won(t.calc_fuel)}`;
  if (!open && t.fuel > 0) return { title: "확정 유류비", value: t.fuel, sub: `모두 마감 · 참고 ${ref}` };
  if (t.fuel > 0) {
    return { title: "유류비 (일부 확정)", value: t.fuel + t.fuel_est, sub: `확정 ${won(t.fuel)} · 미마감 주유 기록 ${won(t.fuel_est)} · 참고 ${ref}` };
  }
  return { title: "NCP 예상 유류비", value: t.ncp_fuel, sub: `마감 전 참고 · 지금까지 주유 기록 ${won(t.fuel_est)} · 오피넷 기준 ${won(t.calc_fuel)}` };
}

function Body({ view, showDays, onShowDays }: { view: CostView; showDays: boolean; onShowDays: (v: boolean) => void }) {
  const t = view.totals;
  const est = t.labor_est + t.ot_expected + t.fuel_est;
  const fc = fuelCard(view);
  return (
    <>
      <section className="stat-grid mt">
        <Card title="순매출" sub="부가세 제외">{won(t.net_revenue)}</Card>
        <Card title="물류비" sub={est ? `예상분 ${won(est)} 포함` : "확정"}>{won(t.cost_total)}</Card>
        <Card title="이익" sub="순매출 − 물류비">{won(t.profit)}</Card>
        <Card title="비용률" sub="물류비 ÷ 순매출">{ratio(t)}</Card>
        <Card title={fc.title} sub={fc.sub}>{won(fc.value)}</Card>
        <Card title="기간" sub={`${view.from} ~ ${view.to}`}>{`${view.days}일 · 영업 ${view.open_days}일`}</Card>
      </section>

      {view.issues.length > 0 && (
        <Panel title="확인 사항">
          {view.issues.map((i, n) => (
            <p key={n} className="small">
              <Chip tone={i.level === "warn" ? "caution" : "neutral"}>{i.level === "warn" ? "확인" : "안내"}</Chip> {i.msg}
            </p>
          ))}
        </Panel>
      )}

      <Panel
        title="계정별"
        desc="단위 원. 매출은 부가세 제외, 비용은 실제 부담액(부가세 공제 차량만 공급가액). 정규직 월급·차량 기간 비용·유류비는 영업일(일요일·공휴일 제외)로 나눠 배분합니다. '예상' 칸은 근무 기록이 없거나 유류비 마감 전인 금액입니다. 맨 오른쪽 4칸(주행 km·주행 시간·NCP 예상 유류비·오피넷 기준)은 지도에 저장된 실제 경로 기준 참고값으로 물류비 합계에 넣지 않습니다. 주행 시간은 NAVER 예상 운전 시간(정차 시간 제외). NCP 예상 유류비는 차량 연비(없으면 NAVER 기본 14km/L), 오피넷 기준은 주행거리 ÷ 차량 연비 × 그날 오피넷 단가이며, 둘 다 연비를 넣거나 바꾸면 지난 날짜도 새 연비로 다시 계산됩니다."
      >
        {view.accounts.length === 0 ? (
          <p className="muted">이 기간에 매출·비용이 없습니다.</p>
        ) : (
          <DataTable columns={[{ label: "계정" }, ...COLUMNS]}>
            {view.accounts.map((a) => (
              <tr key={a.manager_id ?? "none"}>
                <td>{a.manager_name}</td>
                <Cells r={a} />
              </tr>
            ))}
            <tr className="sum">
              <td>합계</td>
              <Cells r={t} />
            </tr>
          </DataTable>
        )}
      </Panel>

      <Panel
        title="일자별"
        right={
          <label className="check">
            <input type="checkbox" checked={showDays} onChange={(e) => onShowDays(e.target.checked)} />
            펼치기
          </label>
        }
      >
        {showDays ? (
          <DataTable columns={[{ label: "일자" }, ...COLUMNS]}>
            {view.by_day.map((d) => {
              const w = WD[new Date(`${d.date}T00:00:00`).getDay()];
              return (
                <tr key={d.date} className={w === "일" ? "off" : undefined}>
                  <td>{d.date.slice(5)} ({w})</td>
                  <Cells r={d} />
                </tr>
              );
            })}
            <tr className="sum">
              <td>합계</td>
              <Cells r={t} />
            </tr>
          </DataTable>
        ) : (
          <p className="muted small">펼치기를 누르면 날짜별 매출·비용을 봅니다 ({view.days}일).</p>
        )}
      </Panel>
    </>
  );
}

export default function LogisticsPage() {
  const isAdmin = Boolean(useMe()?.is_admin);
  const thisMonth = todayKst().slice(0, 7);
  const [mode, setMode] = useState<Mode>("month");
  const [month, setMonth] = useState(thisMonth);
  const [from, setFrom] = useState(monthRange(thisMonth)[0]);
  const [to, setTo] = useState(todayKst());
  const [range, setRange] = useState<[string, string]>(() => monthRange(thisMonth));
  const [tick, setTick] = useState(0);
  const [view, setView] = useState<CostView | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showDays, setShowDays] = useState(false);

  const [qf, qt] = mode === "month" ? monthRange(month) : range;

  useEffect(() => {
    if (!isAdmin) return;
    let alive = true;
    setLoading(true);
    setError("");
    api.getCostView(qf, qt)
      .then((v) => { if (alive) setView(v); })
      .catch((e) => { if (alive) { setView(null); setError(errText(e)); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [qf, qt, tick, isAdmin]);

  function applyRange() {
    if (!from || !to || to < from) return setError("종료일이 시작일보다 빠릅니다");
    if (daysIncl(from, to) > MAX_DAYS) return setError(`조회 기간은 ${MAX_DAYS}일 이내로 지정하세요`);
    setRange([from, to]);
    setTick((n) => n + 1);
  }

  async function exportXlsx() {
    setBusy(true);
    setError("");
    try { await api.exportCostView(qf, qt); } catch (e) { setError(errText(e)); } finally { setBusy(false); }
  }

  const segBtn = (m: Mode, label: string) => (
    <button type="button" className={mode === m ? "on" : undefined} onClick={() => setMode(m)}>{label}</button>
  );

  return (
    <PageLayout
      title="물류비"
      right={
        isAdmin && (
          <div className="row-gap">
            <div className="seg">{segBtn("month", "월")}{segBtn("range", "기간")}</div>
            {mode === "month" ? (
              <input type="month" className="input input-sm" value={month}
                onChange={(e) => e.target.value && setMonth(e.target.value)} />
            ) : (
              <>
                <input type="date" className="input input-sm" value={from} onChange={(e) => setFrom(e.target.value)} />
                <span className="muted">~</span>
                <input type="date" className="input input-sm" value={to} onChange={(e) => setTo(e.target.value)} />
                <Button size="sm" onClick={applyRange}>조회</Button>
              </>
            )}
            <Button size="sm" disabled={!view || busy || loading} onClick={exportXlsx}>엑셀 내보내기</Button>
          </div>
        )
      }
    >
      {!isAdmin ? (
        <Panel><p className="muted">물류비는 관리자만 볼 수 있습니다.</p></Panel>
      ) : (
        <>
          {error && <div className="mt"><ErrorBox message={error} /></div>}
          {loading && <Spinner label="물류비 계산 중… (1년 조회는 처음 20초 정도 걸립니다)" />}
          {!loading && view && <Body view={view} showDays={showDays} onShowDays={setShowDays} />}
        </>
      )}
    </PageLayout>
  );
}
