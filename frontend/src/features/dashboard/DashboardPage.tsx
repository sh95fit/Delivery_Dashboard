import { useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Badge from "@/components/ui/Badge";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import EmptyState from "@/components/ui/EmptyState";
import RetryButton from "@/components/ui/RetryButton";
import StatusCards from "./components/StatusCards";
import ManagerTable from "./components/ManagerTable";
import MapSection from "@/features/map/MapSection";
import { getStatus } from "@/api/status";
import { getDeliveries } from "@/api/deliveries";
import { useAsync } from "@/hooks/useAsync";
import { todayISO } from "@/lib/date";

export default function DashboardPage() {
  const [date, setDate] = useState(todayISO());
  const status = useAsync(() => getStatus(date), [date]);
  const delivery = useAsync(() => getDeliveries(date), [date]);

  const retryAll = () => {
    status.refetch().catch(() => {});
    delivery.refetch().catch(() => {});
  };

  const isLoading = status.loading || delivery.loading;
  const error = status.error || delivery.error;
  const rows = delivery.data?.managers ?? [];
  const stops = delivery.data?.stops ?? [];
  const noData = !isLoading && !error && rows.length === 0;

  return (
    <PageLayout
      title="배송 대시보드"
      right={
        <>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          {status.data && <Badge state={status.data.state} />}
          <span style={{ marginLeft: "auto", fontSize: 12, color: "#666" }}>
            마감: 배송일 전날 14:30 KST
          </span>
        </>
      }
    >
      {error && (
        <div style={{ display: "grid", gap: 12, marginBottom: 16 }}>
          <ErrorBox message={error} />
          <div>
            <RetryButton onClick={retryAll} />
          </div>
        </div>
      )}

      {isLoading && <Spinner />}

      {!error && status.data && <StatusCards status={status.data} />}

      {!error && stops.length > 0 && <MapSection stops={stops} />}

      {!error && noData && (
        <div style={{ marginTop: 24 }}>
          <EmptyState
            title="해당 날짜 데이터가 없습니다"
            description="주문/배송 데이터가 없는 날짜이거나 아직 집계되지 않았습니다."
          />
        </div>
      )}

      {!error && rows.length > 0 && (
        <>
          <h2 style={{ fontSize: 16, margin: "24px 0 8px" }}>매니저별 현황</h2>
          <ManagerTable rows={rows} />
        </>
      )}
    </PageLayout>
  );
}
