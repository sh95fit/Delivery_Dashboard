import DataTable from "@/components/ui/DataTable";
import type { Col } from "@/components/ui/DataTable";
import type { LineupSummary } from "@/api/types";
import { num, orderedLineups, won } from "@/lib/format";

type Props = { byLineup: Record<string, LineupSummary>; internalOn: boolean };

export default function LineupTable({ byLineup, internalOn }: Props) {
  const rows = orderedLineups(byLineup);
  const sum = (f: (v: LineupSummary) => number) => rows.reduce((a, [, v]) => a + f(v), 0);
  const columns: Col[] = [
    "라인업", "구분",
    { label: "수량", num: true }, { label: "환불 수량", num: true },
    { label: "총금액", num: true }, { label: "환불", num: true }, { label: "총금액 − 환불", num: true },
    ...(internalOn ? [{ label: "직원식 수량", num: true }, { label: "직원식 금액", num: true }] : []),
  ];

  return (
    <DataTable columns={columns}>
      {rows.map(([k, v]) => (
        <tr key={k}>
          <td>{v.name}</td>
          <td>{v.meal === "dinner" ? "석식" : "중식"}</td>
          <td className="num">{num(v.qty)}</td>
          <td className="num">{num(v.refund_qty)}</td>
          <td className="num">{won(v.gross_revenue)}</td>
          <td className="num">{won(v.refund_amount)}</td>
          <td className="num">{won(v.net_revenue)}</td>
          {internalOn && <td className="num text-internal">{num(v.internal_qty)}</td>}
          {internalOn && <td className="num text-internal">{won(v.internal_net)}</td>}
        </tr>
      ))}
      <tr className="sum">
        <td>합계</td>
        <td />
        <td className="num">{num(sum((v) => v.qty))}</td>
        <td className="num">{num(sum((v) => v.refund_qty))}</td>
        <td className="num">{won(sum((v) => v.gross_revenue))}</td>
        <td className="num">{won(sum((v) => v.refund_amount))}</td>
        <td className="num">{won(sum((v) => v.net_revenue))}</td>
        {internalOn && <td className="num">{num(sum((v) => v.internal_qty))}</td>}
        {internalOn && <td className="num">{won(sum((v) => v.internal_net))}</td>}
      </tr>
    </DataTable>
  );
}
