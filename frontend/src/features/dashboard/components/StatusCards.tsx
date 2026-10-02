import Card from "@/components/ui/Card";
import type { StatusResp } from "@/api/types";
import { num, won } from "@/lib/format";

export default function StatusCards({ status }: { status: StatusResp }) {
  const t = status.totals;
  const p = status.progress;
  const est = status.state === "PREVIEW" || Boolean(status.estimated);
  const tag = est ? " (예상)" : "";
  const internalOn = Boolean(status.internal?.enabled);
  const pct = p.total > 0 ? Math.round((p.completed / p.total) * 100) : 0;

  return (
    <section>
      <div className="stat-grid">
        <Card title={`배송지${tag}`} sub={t && t.internal_stops > 0 ? `직원식 ${num(t.internal_stops)}곳 포함` : undefined}>
          {num(p.total)}
        </Card>
        {status.state !== "PREVIEW" && <Card title="완료" sub={`${pct}%`}>{num(p.completed)}</Card>}
        <Card title="미배정">{num(p.unassigned)}</Card>
        {status.state === "LIVE" && <Card title="배송전">{num(p.total - p.completed)}</Card>}
        {status.state === "RESULT" && <Card title="미완료">{num(status.incomplete)}</Card>}
        {t && <Card title={`고객사${tag}`}>{num(t.accounts)}</Card>}
      </div>

      {t && (
        <>
          <h3 className="group-title">식수{tag}</h3>
          <div className="stat-grid">
            <Card title="총 식수" sub={internalOn && t.internal_meals > 0 ? `직원식 ${num(t.internal_meals)}식 포함` : undefined}>
              {num(t.meals)}
            </Card>
            <Card title="중식">{num(t.lunch_meals)}</Card>
            <Card title="석식">{num(t.dinner_meals)}</Card>
            <Card title="웹">{num(t.web_qty)}</Card>
            <Card title="어드민">{num(t.admin_qty)}</Card>
            <Card
              title="앱"
              sub={t.app_pending_qty > 0 ? `전환 ${num(t.app_converted_qty)} · 미전환 예상 ${num(t.app_pending_qty)}` : undefined}
            >
              {num(t.app_qty)}
            </Card>
          </div>

          <h3 className="group-title">
            매출{tag} <span className="muted small">VAT 제외{internalOn ? " · 직원식 제외" : ""}</span>
          </h3>
          <div className="stat-grid">
            <Card title="총금액" sub={t.estimated_revenue > 0 ? `앱 미전환 예상분 ${won(t.estimated_revenue)} 포함` : undefined}>
              {won(t.gross_revenue)}
            </Card>
            <Card title="환불금액" sub={t.refund_qty > 0 ? `${num(t.refund_qty)}식` : undefined}>
              {won(t.refund_amount)}
            </Card>
            <Card title="총금액 − 환불">{won(t.net_revenue)}</Card>
          </div>
        </>
      )}
    </section>
  );
}
