import type { CSSProperties } from "react";
import DataTable from "@/components/ui/DataTable";
import type { LineupSummary } from "@/api/types";
import { num, orderedLineups, won } from "@/lib/format";

const td: CSSProperties = { padding: "8px 10px", borderBottom: "1px solid #f0f0f0" };
const tdSum: CSSProperties = { ...td, fontWeight: 700, borderTop: "2px solid #eee" };

type Props = { byLineup: Record<string, LineupSummary>; internalOn: boolean };

export default function LineupTable({ byLineup, internalOn }: Props) {
  const rows = orderedLineups(byLineup);
  const sum = (f: (v: LineupSummary) => number) => rows.reduce((a, [, v]) => a + f(v), 0);
  const columns = [
    "라인업", "구분", "수량", "환불 수량", "총금액", "환불", "총금액 − 환불",
    ...(internalOn ? ["직원식 수량", "직원식 금액"] : []),
  ];

  return (
    <DataTable columns={columns}>
      {rows.map(([k, v]) => (
        <tr key={k}>
          <td style={td}>{v.name}</td>
          <td style={td}>{v.meal === "dinner" ? "석식" : "중식"}</td>
          <td style={td}>{num(v.qty)}</td>
          <td style={td}>{num(v.refund_qty)}</td>
          <td style={td}>{won(v.gross_revenue)}</td>
          <td style={td}>{won(v.refund_amount)}</td>
          <td style={td}>{won(v.net_revenue)}</td>
          {internalOn && <td style={td}>{num(v.internal_qty)}</td>}
          {internalOn && <td style={td}>{won(v.internal_net)}</td>}
        </tr>
      ))}
      <tr>
        <td style={tdSum}>합계</td>
        <td style={tdSum} />
        <td style={tdSum}>{num(sum((v) => v.qty))}</td>
        <td style={tdSum}>{num(sum((v) => v.refund_qty))}</td>
        <td style={tdSum}>{won(sum((v) => v.gross_revenue))}</td>
        <td style={tdSum}>{won(sum((v) => v.refund_amount))}</td>
        <td style={tdSum}>{won(sum((v) => v.net_revenue))}</td>
        {internalOn && <td style={tdSum}>{num(sum((v) => v.internal_qty))}</td>}
        {internalOn && <td style={tdSum}>{won(sum((v) => v.internal_net))}</td>}
      </tr>
    </DataTable>
  );
}
