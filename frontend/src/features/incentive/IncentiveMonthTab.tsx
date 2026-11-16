import { useEffect, useState } from "react";
import Panel from "@/components/ui/Panel";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { getIncMonth } from "@/api/incentive";
import type { IncMonthCell, IncMonthView } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num, todayKst } from "@/lib/format";
import IncentiveAccountModal from "./IncentiveAccountModal";
import { wd } from "./util";

type Props = { month: string; onMonth: (m: string) => void; onPick: (d: string) => void; isAdmin: boolean };

function cellView(c: IncMonthCell, future: boolean): [string, string] {
  if (future) return ["inc-c-future", "예정"];
  if (c.status === "need_accounts") return ["inc-c-need", "입력"];
  if (c.status === "held") return ["inc-c-held", c.extras ? num(c.extras) : "미지급"];
  if (c.status === "no_rate") return ["inc-c-need", "단가"];
  return ["", num(c.total)];
}

export default function IncentiveMonthTab({ month, onMonth, onPick, isAdmin }: Props) {
  const [view, setView] = useState<IncMonthView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ver, setVer] = useState(0);
  // [S2-P4c-3b] 계정별 한 달 입력 창: 이름 → day null, 날짜 칸 → 그 날짜
  const [open, setOpen] = useState<{ mid: number; day: number | null } | null>(null);
  const today = todayKst();

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getIncMonth(month).then((v) => { if (alive) { setView(v); setError(""); } })
      .catch((e) => { if (alive) { setView(null); setError(errText(e)); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [month, ver]);
  useEffect(() => { setOpen(null); }, [month]);

  const days = Array.from({ length: view?.last_day ?? 0 }, (_, i) => i + 1);
  const iso = (d: number) => `${month}-${String(d).padStart(2, "0")}`;
  const opened = open ? view?.people.find((p) => p.manager_id === open.mid) ?? null : null;

  return (
    <Panel
      title={`${month} 인센티브 월 보드`}
      right={<>
        {view?.closed && <Chip tone="warn">마감된 달</Chip>}
        <input type="month" className="input input-sm" value={month} onChange={(e) => e.target.value && onMonth(e.target.value)} />
      </>}
      desc={<>
        칸 = 그날 지급 합계(데일리 인센티브 + 특수 수당). <b>계정 이름</b>을 누르면 그 계정의 한 달 입력,
        <b> 날짜 칸</b>을 누르면 같은 창이 그날로 열립니다 (고객사 수 입력과 [상세]의 제외·조정·미지급·특수 수당·담당 변경까지 한 창에서).
        <b> 날짜 머리글</b>을 누르면 그날 전체 계정의 일자별 입력으로 이동합니다.
      </>}
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
      {loading && !view ? <Spinner /> : view && view.people.length === 0 ? (
        <div className="muted small">이 달에 배송 기록이 없습니다.</div>
      ) : view && (
        <div className="tbl-wrap">
          <table className="tbl inc-month">
            <thead>
              <tr>
                <th>계정</th>
                {days.map((d) => {
                  const w = wd(iso(d));
                  return (
                    <th key={d} className={w === "토" || w === "일" ? "we" : undefined}>
                      <button type="button" className="wl-dayhead" onClick={() => onPick(iso(d))}
                        title={`${d}일 전체 계정 일자별 입력으로 이동`}>{d}<br />{w}</button>
                    </th>
                  );
                })}
                <th>데일리</th><th>특수 수당</th><th>합계</th><th>입력 필요</th>
              </tr>
            </thead>
            <tbody>
              {view.people.map((p) => (
                <tr key={p.manager_id}>
                  <td className="name">
                    <span className="inc-swatch" style={{ background: p.color ?? "#94a3b8" }} />
                    <button type="button" className="wl-namebtn" onClick={() => setOpen({ mid: p.manager_id, day: null })}
                      title="이 계정 한 달 입력">{p.manager_name}</button>
                  </td>
                  {days.map((d) => {
                    const c = p.days[String(d)];
                    if (!c) return <td key={d} className="cell" />;
                    const [cls, label] = cellView(c, iso(d) > today);
                    return (
                      <td key={d} className={`cell ${cls}`} onClick={() => setOpen({ mid: p.manager_id, day: d })}
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
      {open && opened && view && (
        <IncentiveAccountModal
          key={`${month}-${opened.manager_id}-${open.day ?? 0}`}
          month={month} lastDay={view.last_day} person={opened} closed={view.closed} isAdmin={isAdmin}
          focusDay={open.day} rates={view.rates}
          onClose={() => setOpen(null)}
          onChanged={() => setVer((v) => v + 1)}
        />
      )}
    </Panel>
  );
}
