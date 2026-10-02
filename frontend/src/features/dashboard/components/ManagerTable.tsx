import DataTable from "@/components/ui/DataTable";
import type { Col } from "@/components/ui/DataTable";
import type { ManagerRow, StopPoint } from "@/api/types";
import { num, won } from "@/lib/format";

type Props = { rows: ManagerRow[]; stops: StopPoint[]; showProgress: boolean };

export default function ManagerTable({ rows, stops, showProgress }: Props) {
  const done = new Map<string, number>();
  for (const s of stops) {
    if (!s.delivered_at) continue;
    const k = String(s.manager_id ?? "none");
    done.set(k, (done.get(k) ?? 0) + 1);
  }
  const doneOf = (m: ManagerRow) => done.get(String(m.manager_id ?? "none")) ?? 0;
  const sum = (f: (m: ManagerRow) => number) => rows.reduce((a, m) => a + f(m), 0);

  const columns: Col[] = [
    "매니저",
    { label: "배송지", num: true },
    ...(showProgress ? [{ label: "완료", num: true }] : []),
    { label: "식수", num: true }, { label: "중식", num: true }, { label: "석식", num: true },
    { label: "고객사", num: true }, { label: "총금액 − 환불", num: true },
  ];

  return (
    <DataTable columns={columns}>
      {rows.map((m) => (
        <tr key={m.manager_id ?? "none"}>
          <td>
            {m.color && <span className="dot" style={{ background: m.color }} />}
            {m.manager_id == null ? "미배정" : m.manager_name ?? m.manager_id}
          </td>
          <td className="num">
            {num(m.stops)}
            {m.internal_stops > 0 && <span className="text-internal tag-inline">직원식 {m.internal_stops}</span>}
          </td>
          {showProgress && <td className="num">{num(doneOf(m))} / {num(m.stops)}</td>}
          <td className="num">{num(m.meals)}</td>
          <td className="num">{num(m.lunch_meals)}</td>
          <td className="num">{num(m.dinner_meals)}</td>
          <td className="num">{num(m.accounts)}</td>
          <td className="num">{won(m.net_revenue)}</td>
        </tr>
      ))}
      <tr className="sum">
        <td>합계</td>
        <td className="num">{num(sum((m) => m.stops))}</td>
        {showProgress && <td className="num">{num(sum(doneOf))} / {num(sum((m) => m.stops))}</td>}
        <td className="num">{num(sum((m) => m.meals))}</td>
        <td className="num">{num(sum((m) => m.lunch_meals))}</td>
        <td className="num">{num(sum((m) => m.dinner_meals))}</td>
        <td className="num">-</td>
        <td className="num">{won(sum((m) => m.net_revenue))}</td>
      </tr>
    </DataTable>
  );
}
