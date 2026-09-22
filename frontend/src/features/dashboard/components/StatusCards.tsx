import Card from "@/components/ui/Card";
import type { StatusResp } from "@/api/types";

export default function StatusCards({ status }: { status: StatusResp }) {
  return (
    <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12 }}>
      <Card title="배송지">
        {status.state === "PREVIEW" && status.estimate
          ? `${status.estimate.total} (예상)`
          : status.progress.total}
      </Card>
      <Card title="완료">{status.progress.completed}</Card>
      <Card title="미배정">{status.progress.unassigned}</Card>
      <Card title="미완료">{status.incomplete}</Card>
      {status.state === "PREVIEW" && status.estimate && (
        <>
          <Card title="예상 식수">{status.estimate.estimated_meals}</Card>
          <Card title="예상 고객사">{status.estimate.estimated_accounts}</Card>
        </>
      )}
    </section>
  );
}
