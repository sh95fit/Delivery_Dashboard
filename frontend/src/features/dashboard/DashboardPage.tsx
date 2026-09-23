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
import { getAllRoutes, type AllRoutesResp } from "@/api/routes";
import { useAsync } from "@/hooks/useAsync";
import { usePolling } from "@/hooks/usePolling";
import { todayISO } from "@/lib/date";

export default function DashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [selectedManagerId, setSelectedManagerId] = useState<number | null>(null);
  const [routesData, setRoutesData] = useState<AllRoutesResp | null>(null);
  const [routesLoading, setRoutesLoading] = useState(false);
  const [routesError, setRoutesError] = useState("");

  const status = useAsync(() => getStatus(date), [date]);
  const delivery = useAsync(() => getDeliveries(date), [date]);

  const shouldPoll = status.data?.state === "PREVIEW" || status.data?.state === "LIVE";

  const rows = delivery.data?.managers ?? [];
  const stops = delivery.data?.stops ?? [];
  const noData = !status.loading && !delivery.loading && !status.error && !delivery.error && rows.length === 0;
  const source = delivery.data?.source;

  const managerOptions = useMemo(
    () => rows.filter((x) => x.manager_id != null),
    [rows],
  );

  const displayedRoutes = useMemo(() => {
    if (!routesData) return [];
    if (selectedManagerId == null) return routesData.routes;
    return routesData.routes.filter((r) => r.manager_id === selectedManagerId);
  }, [routesData, selectedManagerId]);

  async function loadRoutes() {
    setRoutesLoading(true);
    setRoutesError("");
    try {
      const data = await getAllRoutes(date);
      setRoutesData(data);
    } catch (e) {
      setRoutesError(e instanceof Error ? e.message : String(e));
      setRoutesData(null);
    } finally {
      setRoutesLoading(false);
    }
  }

  const retryAll = () => {
    status.refetch().catch(() => {});
    delivery.refetch().catch(() => {});
    loadRoutes().catch(() => {});
  };

  useEffect(() => {
    loadRoutes().catch(() => {});
  }, [date]);

  usePolling(() => {
    status.refetch().catch(() => {});
    delivery.refetch().catch(() => {});
    loadRoutes().catch(() => {});
  }, 30000, Boolean(shouldPoll));

  const isLoading = status.loading || delivery.loading || routesLoading;
  const error = status.error || delivery.error || routesError;

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
        <div style={{ marginTop: 16, marginBottom: 8, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <label htmlFor="manager-select" style={{ fontSize: 14, fontWeight: 600 }}>
            노선 강조 매니저
          </label>
          <select
            id="manager-select"
            value={selectedManagerId ?? ""}
            onChange={(e) => setSelectedManagerId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">전체 노선</option>
            {managerOptions.map((m) => (
              <option key={m.manager_id} value={m.manager_id}>
                {m.manager_name ?? m.manager_id}
              </option>
            ))}
          </select>
          {routesLoading && <span style={{ fontSize: 12, color: "#666" }}>경로 불러오는 중…</span>}
        </div>
      )}

      {!error && stops.length > 0 && (
        <MapSection stops={stops} routes={displayedRoutes} selectedManagerId={selectedManagerId} />
      )}

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
