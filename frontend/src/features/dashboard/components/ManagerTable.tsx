import type { LineupMeta, ManagerRow, StopPoint } from "@/api/types";
import { num, won } from "@/lib/format";

type Props = { rows: ManagerRow[]; stops: StopPoint[]; showProgress: boolean; meta: LineupMeta[] };

const Q = (v: number, cls: string | undefined, key: string) => (
  <td key={key} className={cls ? `num ${cls}` : "num"}>{v ? num(v) : <span className="zero">-</span>}</td>
);

export default function ManagerTable({ rows, stops, showProgress, meta }: Props) {
  const done = new Map<string, number>();
  for (const s of stops) {
    if (!s.delivered_at) continue;
    const k = String(s.manager_id ?? "none");
    done.set(k, (done.get(k) ?? 0) + 1);
  }
  const doneOf = (m: ManagerRow) => done.get(String(m.manager_id ?? "none")) ?? 0;
  const sum = (f: (m: ManagerRow) => number) => rows.reduce((a, m) => a + f(m), 0);
  const qty = (m: ManagerRow, id: string) => m.lineups?.[id]?.qty ?? 0;

  const groups = [
    { key: "lunch", label: "중식", items: meta.filter((x) => x.meal !== "dinner") },
    { key: "dinner", label: "석식", items: meta.filter((x) => x.meal === "dinner") },
  ];

  const lineupCells = (get: (id: string) => number, totals: [number, number]) =>
    groups.flatMap((g, gi) => [
      ...g.items.map((l, i) => Q(get(l.id), i === 0 ? "bl" : undefined, `${g.key}-${l.id}`)),
      Q(totals[gi], g.items.length === 0 ? "bl sub" : "sub", `${g.key}-sum`),
    ]);

  const refund = (v: number) => (v ? <span className="neg">−{won(v)}</span> : <span className="zero">-</span>);

  return (
    <div className="tbl-wrap">
      <table className="tbl tbl-group">
        <thead>
          <tr>
            <th rowSpan={2}>매니저</th>
            <th rowSpan={2} className="num">배송지</th>
            {showProgress && <th rowSpan={2} className="num">완료</th>}
            <th rowSpan={2} className="num">식수</th>
            {groups.map((g) => (
              <th key={g.key} colSpan={g.items.length + 1} className="grp bl">{g.label}</th>
            ))}
            <th rowSpan={2} className="num bl">고객사</th>
            <th colSpan={3} className="grp bl">금액</th>
          </tr>
          <tr>
            {groups.flatMap((g) => [
              ...g.items.map((l, i) => <th key={`${g.key}-${l.id}`} className={i === 0 ? "num bl" : "num"}>{l.label}</th>),
              <th key={`${g.key}-sum`} className={g.items.length === 0 ? "num bl sub" : "num sub"}>계</th>,
            ])}
            <th className="num bl">매출</th>
            <th className="num">환불</th>
            <th className="num">매출 − 환불</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.manager_id ?? "none"}>
              <td>
                <span className="dot" style={{ background: m.color ?? "var(--faint)" }} />
                {m.manager_id == null ? "미배정" : m.manager_name ?? `#${m.manager_id}`}
              </td>
              <td className="num">
                {num(m.stops)}
                {m.internal_stops > 0 && <span className="text-internal tag-inline">직원식 {m.internal_stops}</span>}
              </td>
              {showProgress && <td className="num">{num(doneOf(m))} / {num(m.stops)}</td>}
              <td className="num">{num(m.meals)}</td>
              {lineupCells((id) => qty(m, id), [m.lunch_meals, m.dinner_meals])}
              <td className="num bl">{num(m.accounts)}</td>
              <td className="num bl">{won(m.gross_revenue)}</td>
              <td className="num">{refund(m.refund_amount)}</td>
              <td className="num">{won(m.net_revenue)}</td>
            </tr>
          ))}
          <tr className="sum">
            <td>합계</td>
            <td className="num">{num(sum((m) => m.stops))}</td>
            {showProgress && <td className="num">{num(sum(doneOf))} / {num(sum((m) => m.stops))}</td>}
            <td className="num">{num(sum((m) => m.meals))}</td>
            {lineupCells((id) => sum((m) => qty(m, id)), [sum((m) => m.lunch_meals), sum((m) => m.dinner_meals)])}
            <td className="num bl">-</td>
            <td className="num bl">{won(sum((m) => m.gross_revenue))}</td>
            <td className="num">{refund(sum((m) => m.refund_amount))}</td>
            <td className="num">{won(sum((m) => m.net_revenue))}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
