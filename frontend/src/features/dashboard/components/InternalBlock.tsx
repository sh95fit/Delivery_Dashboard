import type { CSSProperties } from "react";
import DataTable from "@/components/ui/DataTable";
import type { InternalView } from "@/api/types";
import { num, orderedLineups, won } from "@/lib/format";

const td: CSSProperties = { padding: "8px 10px", borderBottom: "1px solid #f0f0f0" };

export default function InternalBlock({ internal, est }: { internal?: InternalView | null; est: boolean }) {
  if (!internal || !internal.enabled) return null;
  const lineups = orderedLineups(internal.by_lineup ?? {}).filter(([, v]) => v.qty > 0);

  return (
    <section style={{ marginTop: 24, border: "1px solid #ddd6fe", background: "#faf5ff", borderRadius: 10, padding: 16 }}>
      <h2 style={{ fontSize: 16, margin: "0 0 4px" }}>직원식 {est ? "(예상)" : ""}</h2>
      <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>
        수량과 배송지는 위 합계에 포함되어 있고, 금액은 매출에서 빠진 값입니다 (VAT 제외).
      </div>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 14, marginBottom: 12 }}>
        <span>배송지 <b>{num(internal.stops)}</b>곳</span>
        <span>식수 <b>{num(internal.meals)}</b>식</span>
        <span>
          금액 <b>{won(internal.net_revenue)}</b>
          {internal.refund_amount > 0
            ? ` (총 ${won(internal.gross_revenue)} − 환불 ${won(internal.refund_amount)})`
            : ""}
        </span>
        {lineups.length > 0 && (
          <span style={{ color: "#555" }}>{lineups.map(([, v]) => `${v.name} ${num(v.qty)}`).join(" · ")}</span>
        )}
      </div>
      {internal.places.length > 0 && (
        <DataTable columns={["배송지", "매니저", "식수", "금액", "완료"]}>
          {internal.places.map((p, i) => (
            <tr key={`${p.address_id ?? "x"}-${i}`}>
              <td style={td}>{p.address_name ?? p.address_id}</td>
              <td style={td}>{p.manager_name ?? "미배정"}</td>
              <td style={td}>{num(p.meals)}</td>
              <td style={td}>{won(p.net_revenue)}</td>
              <td style={td}>{p.delivered ? "완료" : "-"}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </section>
  );
}
