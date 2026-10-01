import type { CSSProperties } from "react";
import DataTable from "@/components/ui/DataTable";
import type { ManagerRow, StopPoint } from "@/api/types";
import { num, won } from "@/lib/format";

const td: CSSProperties = { padding: "8px 10px", borderBottom: "1px solid #f0f0f0" };
const tdSum: CSSProperties = { ...td, fontWeight: 700, borderTop: "2px solid #eee" };

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

  const columns = [
    "매니저", "배송지", ...(showProgress ? ["완료"] : []),
    "식수", "중식", "석식", "고객사", "총금액 − 환불",
  ];

  return (
    <DataTable columns={columns}>
      {rows.map((m) => (
        <tr key={m.manager_id ?? "none"}>
          <td style={td}>
            {m.color && (
              <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 9999, background: m.color, marginRight: 6 }} />
            )}
            {m.manager_id == null ? "미배정" : m.manager_name ?? m.manager_id}
          </td>
          <td style={td}>
            {num(m.stops)}
            {m.internal_stops > 0 && (
              <span style={{ color: "#7c3aed", fontSize: 11, marginLeft: 6 }}>직원식 {m.internal_stops}</span>
            )}
          </td>
          {showProgress && <td style={td}>{num(doneOf(m))} / {num(m.stops)}</td>}
          <td style={td}>{num(m.meals)}</td>
          <td style={td}>{num(m.lunch_meals)}</td>
          <td style={td}>{num(m.dinner_meals)}</td>
          <td style={td}>{num(m.accounts)}</td>
          <td style={td}>{won(m.net_revenue)}</td>
        </tr>
      ))}
      <tr>
        <td style={tdSum}>합계</td>
        <td style={tdSum}>{num(sum((m) => m.stops))}</td>
        {showProgress && <td style={tdSum}>{num(sum(doneOf))} / {num(sum((m) => m.stops))}</td>}
        <td style={tdSum}>{num(sum((m) => m.meals))}</td>
        <td style={tdSum}>{num(sum((m) => m.lunch_meals))}</td>
        <td style={tdSum}>{num(sum((m) => m.dinner_meals))}</td>
        <td style={tdSum}>-</td>
        <td style={tdSum}>{won(sum((m) => m.net_revenue))}</td>
      </tr>
    </DataTable>
  );
}
