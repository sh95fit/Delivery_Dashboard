import { useEffect, useMemo, useState } from "react";
import Panel from "@/components/ui/Panel";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import type { ManagerRow } from "@/api/masters";
import { INCOME_LABEL } from "@/api/workers";
import { getWorkMonth, hmm } from "@/api/worklogs";
import type { WorkMonthView } from "@/api/worklogs";
import { errText } from "@/lib/form";
import { num, won } from "@/lib/format";
import WorkPersonModal from "./WorkPersonModal";

type Filter = "all" | "labor" | "business";
const FILTERS: Array<[Filter, string]> = [["all", "전체"], ["labor", "근로소득"], ["business", "사업소득"]];
const WD = "일월화수목금토";

type Props = {
  month: string; onMonth: (m: string) => void;
  managers: ManagerRow[]; isAdmin: boolean; onSaved: () => void;
};

export default function WorkMonthTab({ month, onMonth, managers, isAdmin, onSaved }: Props) {
  const [view, setView] = useState<WorkMonthView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [ver, setVer] = useState(0);
  const [edit, setEdit] = useState<{ wid: number; day: number | null } | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getWorkMonth(`${month}-01`)
      .then((v) => { if (alive) { setView(v); setError(""); } })
      .catch((e) => { if (alive) { setView(null); setError(errText(e)); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [month, ver]);
  useEffect(() => { setNote(""); setEdit(null); }, [month]);

  const [y, m] = month.split("-").map(Number);
  const all = view?.people ?? [];
  const days = useMemo(() => Array.from({ length: view?.last_day ?? 0 }, (_, i) => i + 1), [view]);
  const people = useMemo(() => all.filter((p) => filter === "all" || p.sheet === filter), [all, filter]);
  const tot = useMemo(() => people.reduce((a, p) => ({
    days: a.days + p.summary.days, paid: a.paid + p.summary.paid_min, base: a.base + p.summary.base,
    sheet: a.sheet + p.pay.sheet.total, ot: a.ot + p.summary.ot_min, otPay: a.otPay + (p.pay.ot_allow ?? 0),
    exp: a.exp + (p.pay.expected?.total ?? p.pay.sheet.total),
  }), { days: 0, paid: 0, base: 0, sheet: 0, ot: 0, otPay: 0, exp: 0 }), [people]);
  const count = (f: Filter) => all.filter((p) => f === "all" || p.sheet === f).length;
  const editing = edit ? all.find((p) => p.worker_id === edit.wid) ?? null : null;

  return (
    <Panel
      title={`${y}년 ${m}월 · ${num(people.length)}명`}
      right={
        <>
          {view && (view.closed ? <Chip tone="ok">마감</Chip> : <Chip>미마감</Chip>)}
          <div className="seg">
            {FILTERS.map(([k, label]) => (
              <button key={k} type="button" className={filter === k ? "on" : undefined} onClick={() => setFilter(k)}>
                {label} {num(count(k))}
              </button>
            ))}
          </div>
          <input type="month" className="input input-sm" value={month} onChange={(e) => e.target.value && onMonth(e.target.value)} />
        </>
      }
      desc={<>
        <b>이름</b>을 누르면 그 사람의 한 달 입력, <b>날짜 칸</b>을 누르면 같은 창이 그날로 열립니다.
        <b> 근무표 지급</b> = 엑셀 총지급액 (기본급 + 월 수당, 사업자는 부가세 포함, 초과수당 제외).
        회색 <b>예상</b> 칸은 초과 기준이 있는 사람만 참고로 표시하며 엑셀에는 들어가지 않습니다.
      </>}
    >
      {error && <ErrorBox message={error} />}
      {note && <div className="notice mt">✓ {note}</div>}
      {loading && !view ? (
        <Spinner />
      ) : people.length === 0 ? (
        <div className="muted small">이 달 근무 기록·대상이 없습니다.</div>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl wl-month">
            <thead>
              <tr>
                <th className="wl-name">이름</th>
                {days.map((d) => {
                  const w = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
                  return <th key={d} className={w === 0 ? "wl-sun" : w === 6 ? "wl-sat" : undefined}>{d}<br />{WD[w]}</th>;
                })}
                <th className="num">근무일</th>
                <th className="num">유급시간</th>
                <th className="num">기본급</th>
                <th className="num">근무표 지급</th>
                <th className="num wl-exp">계약 외</th>
                <th className="num wl-exp">예상 초과수당</th>
                <th className="num wl-exp">예상 총액</th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.worker_id} className={p.active ? undefined : "off"}>
                  <td className="wl-name">
                    <button type="button" className="wl-namebtn" onClick={() => setEdit({ wid: p.worker_id, day: null })}
                      title="한 달 입력 열기">
                      {p.name}
                    </button>{" "}
                    <span className="muted small">{INCOME_LABEL[p.income_type]}</span>
                    {p.summary.nocontract > 0 && <> <Chip tone="danger">계약 없는 날 {p.summary.nocontract}</Chip></>}
                  </td>
                  {days.map((d) => {
                    const lg = p.days[String(d)];
                    const open = () => setEdit({ wid: p.worker_id, day: d });
                    return (
                      <td key={d}>
                        {lg ? (
                          <button type="button" className={`wl-cell${lg.no_contract ? " wl-bad" : ""}`} onClick={open}
                            title={`출근 ${lg.clock_in}${lg.punch_in ? ` (지문 ${lg.punch_in})` : ""} · 퇴근 ${lg.clock_out} · 휴게 ${lg.sheet_break ?? 0}분${lg.memo ? ` · ${lg.memo}` : ""}`}>
                            <span>{lg.clock_in}</span><span>{lg.clock_out}</span><b>{hmm(lg.paid_min)}</b>
                          </button>
                        ) : (
                          <button type="button" className="wl-cell wl-empty" onClick={open} aria-label={`${d}일 입력`}>·</button>
                        )}
                      </td>
                    );
                  })}
                  <td className="num">{num(p.summary.days)}</td>
                  <td className="num">{hmm(p.summary.paid_min)}</td>
                  <td className="num">{won(p.summary.base)}</td>
                  <td className="num" title={`공급가 ${won(p.pay.sheet.supply)} + 부가세 ${won(p.pay.sheet.vat)}`}><b>{won(p.pay.sheet.total)}</b></td>
                  <td className="num wl-exp">{hmm(p.summary.ot_min)}</td>
                  <td className="num wl-exp">{p.pay.ot_allow == null ? "기준 없음" : won(p.pay.ot_allow)}</td>
                  <td className="num wl-exp">{p.pay.expected ? won(p.pay.expected.total) : "-"}</td>
                </tr>
              ))}
              <tr className="wl-total">
                <td className="wl-name">합계</td>
                <td colSpan={days.length} />
                <td className="num">{num(tot.days)}</td>
                <td className="num">{hmm(tot.paid)}</td>
                <td className="num">{won(tot.base)}</td>
                <td className="num">{won(tot.sheet)}</td>
                <td className="num wl-exp">{hmm(tot.ot)}</td>
                <td className="num wl-exp">{won(tot.otPay)}</td>
                <td className="num wl-exp" title="기준 없는 사람은 근무표 지급액으로 합산">{won(tot.exp)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {editing && view && (
        <WorkPersonModal
          key={`${editing.worker_id}-${month}`}
          person={editing} month={month} lastDay={view.last_day} focusDay={edit?.day ?? null}
          closed={view.closed} isAdmin={isAdmin} managers={managers}
          onClose={() => setEdit(null)}
          onSaved={(msg) => { setEdit(null); setNote(msg); setVer((v) => v + 1); onSaved(); }}
        />
      )}
    </Panel>
  );
}
