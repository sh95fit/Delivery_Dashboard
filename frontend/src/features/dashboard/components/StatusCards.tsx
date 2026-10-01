import type { CSSProperties, ReactNode } from "react";
import type { StatusResp } from "@/api/types";
import { num, won } from "@/lib/format";

function Stat({ title, value, sub }: { title: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: "12px 16px", background: "#fff" }}>
      <div style={{ fontSize: 12, color: "#666" }}>{title}</div>
      <div style={{ fontSize: 22, fontWeight: 700, marginTop: 2 }}>{value}</div>
      {sub ? <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>{sub}</div> : null}
    </div>
  );
}

const grid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
  gap: 12,
};
const groupTitle: CSSProperties = { fontSize: 13, fontWeight: 700, color: "#444", margin: "16px 0 8px" };

export default function StatusCards({ status }: { status: StatusResp }) {
  const t = status.totals;
  const p = status.progress;
  const est = status.state === "PREVIEW" || Boolean(status.estimated);
  const tag = est ? " (예상)" : "";
  const internalOn = Boolean(status.internal?.enabled);
  const pct = p.total > 0 ? Math.round((p.completed / p.total) * 100) : 0;

  return (
    <section>
      <div style={grid}>
        <Stat
          title={`배송지${tag}`}
          value={num(p.total)}
          sub={t && t.internal_stops > 0 ? `직원식 ${num(t.internal_stops)}곳 포함` : undefined}
        />
        {status.state !== "PREVIEW" && <Stat title="완료" value={num(p.completed)} sub={`${pct}%`} />}
        <Stat title="미배정" value={num(p.unassigned)} />
        {status.state === "LIVE" && <Stat title="남은 배송지" value={num(p.total - p.completed)} />}
        {status.state === "RESULT" && <Stat title="미완료" value={num(status.incomplete)} />}
        {t && <Stat title={`고객사${tag}`} value={num(t.accounts)} />}
      </div>

      {t && (
        <>
          <div style={groupTitle}>식수{tag}</div>
          <div style={grid}>
            <Stat
              title="총 식수"
              value={num(t.meals)}
              sub={internalOn && t.internal_meals > 0 ? `직원식 ${num(t.internal_meals)}식 포함` : undefined}
            />
            <Stat title="중식" value={num(t.lunch_meals)} />
            <Stat title="석식" value={num(t.dinner_meals)} />
            <Stat title="웹" value={num(t.web_qty)} />
            <Stat title="어드민" value={num(t.admin_qty)} />
            <Stat
              title="앱"
              value={num(t.app_qty)}
              sub={
                t.app_pending_qty > 0
                  ? `전환 ${num(t.app_converted_qty)} · 미전환 예상 ${num(t.app_pending_qty)}`
                  : undefined
              }
            />
          </div>

          <div style={groupTitle}>
            매출{tag} · VAT 제외{internalOn ? " · 직원식 제외" : ""}
          </div>
          <div style={grid}>
            <Stat
              title="총금액"
              value={won(t.gross_revenue)}
              sub={t.estimated_revenue > 0 ? `앱 미전환 예상분 ${won(t.estimated_revenue)} 포함` : undefined}
            />
            <Stat
              title="환불금액"
              value={won(t.refund_amount)}
              sub={t.refund_qty > 0 ? `${num(t.refund_qty)}식` : undefined}
            />
            <Stat title="총금액 − 환불" value={won(t.net_revenue)} />
          </div>
        </>
      )}
    </section>
  );
}
