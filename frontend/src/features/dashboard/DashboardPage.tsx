import { useEffect, useMemo, useState } from "react";
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
import { getRoute, type RouteResp } from "@/api/routes";
import { useAsync } from "@/hooks/useAsync";
import { usePolling } from "@/hooks/usePolling";
import { todayISO } from "@/lib/date";

export default function DashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [selectedManagerId, setSelectedManagerId] = useState<number | null>(null);
  const [route, setRoute] = useState<RouteResp | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);

  const status = useAsync(() => getStatus(date), [date]);
  const delivery = useAsync(() => getDeliveries(date), [date]);

  const shouldPoll = status.data?.state === "PREVIEW" || status.data?.state === "LIVE";

  const retryAll = () => {
    status.refetch().catch(() => {});
    delivery.refetch().catch(() => {});
    if (selectedManagerId != null) {
      loadRoute(selectedManagerId).catch(() => {});
    }
  };

  const isLoading = status.loading || delivery.loading;
  const error = status.error || delivery.error;
  const rows = delivery.data?.managers ?? [];
  const stops = delivery.data?.stops ?? [];
  const noData = !isLoading && !error && rows.length === 0;
  const source = delivery.data?.source;

  const managerOptions = useMemo(
    () => rows.filter((x) => x.manager_id != null),
    [rows],
  );

  async function loadRoute(managerId: number) {
    setRouteLoading(true);
    try {
      const data = await getRoute(date, managerId);
      setRoute(data);
    } catch {
      setRoute(null);
    } finally {
      setRouteLoading(false);
    }
  }

  useEffect(() => {
    if (selectedManagerId == null) {
      setRoute(null);
      return;
    }
    loadRoute(selectedManagerId).catch(() => {});
  }, [date, selectedManagerId]);

  usePolling(() => {
    status.refetch().catch(() => {});
    delivery.refetch().catch(() => {});
    if (selectedManagerId != null) {
      loadRoute(selectedManagerId).catch(() => {});
    }
  }, 30000, Boolean(shouldPoll));

  return (
    <PageLayout
      title="배송 대시보드"
      right={
        <>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          {status.data && <Badge state={status.data.state} />}
          {source === "orders_estimate" && (
            <span style={{ fontSize: 12, color: "#8b8b00", fontWeight: 700 }}>
              예상치 기준
            </span>
          )}
          {shouldPoll && (
            <span style={{ fontSize: 12, color: "#c62828", fontWeight: 700 }}>
              30초 갱신 중
            </span>
          )}
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

      {!error && managerOptions.length > 0 && (
        <div style={{ marginTop: 16, marginBottom: 8, display: "flex", gap: 12, alignItems: "center" }}>
          <label htmlFor="manager-select" style={{ fontSize: 14, fontWeight: 600 }}>
            경로 조회 매니저
          </label>
          <select
            id="manager-select"
            value={selectedManagerId ?? ""}
            onChange={(e) => setSelectedManagerId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">선택 안 함</option>
            {managerOptions.map((m) => (
              <option key={m.manager_id} value={m.manager_id}>
                {m.manager_name ?? m.manager_id}
              </option>
            ))}
          </select>
          {routeLoading && <span style={{ fontSize: 12, color: "#666" }}>경로 불러오는 중…</span>}
        </div>
      )}

      {!error && stops.length > 0 && <MapSection stops={stops} route={route} />}

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
          <h2 style={{ fontSize: 16, margin: "24px 0 8px" }}>
            매니저별 현황 {source === "orders_estimate" ? "(예상)" : ""}
          </h2>
          <ManagerTable rows={rows} />
        </>
      )}
    </PageLayout>
  );
}
