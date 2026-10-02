import Panel from "@/components/ui/Panel";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import type { InternalView } from "@/api/types";
import { num, orderedLineups, won } from "@/lib/format";

export default function InternalBlock({ internal, est }: { internal?: InternalView | null; est: boolean }) {
  if (!internal || !internal.enabled) return null;
  const lineups = orderedLineups(internal.by_lineup ?? {}).filter(([, v]) => v.qty > 0);

  return (
    <Panel
      tone="internal"
      title={`직원식${est ? " (예상)" : ""}`}
      desc="수량과 배송지는 위 합계에 포함되어 있고, 금액은 매출에서 빠진 값입니다 (VAT 제외)."
    >
      <div className="inline-stats">
        <span>배송지 <b>{num(internal.stops)}</b>곳</span>
        <span>식수 <b>{num(internal.meals)}</b>식</span>
        <span>
          금액 <b>{won(internal.net_revenue)}</b>
          {internal.refund_amount > 0 ? ` (총 ${won(internal.gross_revenue)} − 환불 ${won(internal.refund_amount)})` : ""}
        </span>
        {lineups.length > 0 && <span className="muted">{lineups.map(([, v]) => `${v.name} ${num(v.qty)}`).join(" · ")}</span>}
      </div>
      {internal.places.length > 0 && (
        <DataTable columns={["배송지", "매니저", { label: "식수", num: true }, { label: "금액", num: true }, "완료"]}>
          {internal.places.map((p, i) => (
            <tr key={`${p.address_id ?? "x"}-${i}`}>
              <td>{p.address_name ?? p.address_id}</td>
              <td>{p.manager_name ?? "미배정"}</td>
              <td className="num">{num(p.meals)}</td>
              <td className="num">{won(p.net_revenue)}</td>
              <td>{p.delivered ? <Chip tone="ok">완료</Chip> : <span className="muted">-</span>}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </Panel>
  );
}
