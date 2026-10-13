import { useEffect, useState } from "react";
import Panel from "@/components/ui/Panel";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { getIncMonth } from "@/api/incentive";
import type { IncMonthCell, IncMonthView } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num, todayKst } from "@/lib/format";
import { wd } from "./util";

type Props = { month: string; onMonth: (m: string) => void; onPick: (d: string) => void };

function cellView(c: IncMonthCell, future: boolean): [string, string] {
  if (future) return ["inc-c-future", "예정"];
  if (c.status === "need_accounts") return ["inc-c-need", "입력"];
  if (c.status === "held") return ["inc-c-held", c.extras ? num(c.extras) : "미지급"];
  if (c.status === "no_rate") return ["inc-c-need", "단가"];
  return ["", num(c.total)];
}

export default function IncentiveMonthTab({ month, onMonth, onPick }: Props) {
  const [view, setView] = useState<IncMonthView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const today = todayKst();

  useEffect(() => {
    setLoading(true);
    getIncMonth(month).then((v) => { setView(v); setError(""); })
      .catch((e) => { setView(null); setError(errText(e)); })
      .finally(() => setLoading(false));
  }, [month]);

  const days = Array.from({ length: view?.last_day ?? 0 }, (_, i) => i + 1);
  const iso = (d: number) => `${month}-${String(d).padStart(2, "0")}`;

  return (
    <Panel
      title={`${month} 인센티브 월 보드`}
      right={<>
        {view?.closed && <Chip tone="warn">마감된 달</Chip>}
        <input type="month" className="input input-sm" value={month} onChange={(e) => e.target.value && onMonth(e.target.value)} />
      </>}
      desc="칸 = 그날 지급 합계(데일리 인센티브 + 특수 수당). 칸을 누르면 그 날짜의 일자별 입력으로 이동합니다."
    >
      {error && <ErrorBox message={error} />}
      <div className="inc-legend">
        <span className="lg-need">고객사 수 입력 필요</span>
        <span className="lg-held">미지급 (숫자 = 특수 수당만)</span>
        <span className="lg-extra"><i className="inc-dot" />특수 수당 있음</span>
      </div>
      {view && (
        <div className="muted small">
          월 합계 {num(view.totals.total)}원 (데일리 {num(view.totals.incentive)} + 특수 수당 {num(view.totals.extras)})
          {view.totals.pending_days > 0 && ` · 입력 필요 ${num(view.totals.pending_days)}건 (이 건은 합계에서 빠짐)`}
        </div>
      )}
      {loading ? <Spinner /> : view && view.people.length === 0 ? (
        <div className="muted small">이 달에 배송 기록이 없습니다.</div>
      ) : view && (
        <div className="tbl-wrap">
          <table className="tbl inc-month">
            <thead>
              <tr>
                <th>계정</th>
                {days.map((d) => {
                  const w = wd(iso(d));
                  return <th key={d} className={w === "토" || w === "일" ? "we" : undefined}>{d}<br />{w}</th>;
                })}
                <th>데일리</th><th>특수 수당</th><th>합계</th><th>입력 필요</th>
              </tr>
            </thead>
            <tbody>
              {view.people.map((p) => (
                <tr key={p.manager_id}>
                  <td className="name"><span className="inc-swatch" style={{ background: p.color ?? "#94a3b8" }} />{p.manager_name}</td>
                  {days.map((d) => {
                    const c = p.days[String(d)];
                    if (!c) return <td key={d} className="cell" onClick={() => onPick(iso(d))} />;
                    const [cls, label] = cellView(c, iso(d) > today);
                    return (
                      <td key={d} className={`cell ${cls}`} onClick={() => onPick(iso(d))}
                        title={`제품 ${num(c.product_total)} · 고객사 ${c.accounts ?? "미입력"} · 특수 수당 ${num(c.extras)}원${c.warn ? " · ⚠ 확인 필요" : ""}`}>
                        <span className="inc-cv">{label}{c.extras > 0 && <i className="inc-dot" />}{c.warn && <em className="inc-cw">⚠</em>}</span>
                      </td>
                    );
                  })}
                  <td className="num">{num(p.sum.incentive)}</td>
                  <td className="num">{num(p.sum.extras)}</td>
                  <td className="num"><b>{num(p.sum.total)}</b></td>
                  <td className="num">{p.sum.pending_days ? <Chip tone="caution">{p.sum.pending_days}</Chip> : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
