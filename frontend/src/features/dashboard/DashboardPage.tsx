import { useEffect, useMemo, useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Badge from "@/components/ui/Badge";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import EmptyState from "@/components/ui/EmptyState";
import RetryButton from "@/components/ui/RetryButton";
import StatusCards from "./components/StatusCards";
import ManagerTable from "./components/ManagerTable";
import WarningsBar from "./components/WarningsBar";
import LineupTable from "./components/LineupTable";
import InternalBlock from "./components/InternalBlock";
import MapSection from "@/features/map/MapSection";
import { getStatus } from "@/api/status";
import { getDeliveries } from "@/api/deliveries";
import { getAllRoutes } from "@/api/routes";
import type { AllRoutesResp, ManagerRow } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { usePolling } from "@/hooks/usePolling";
import { todayISO } from "@/lib/date";
import { kstDateTime } from "@/lib/format";
import { Link } from "react-router-dom";

type AssignedManager = ManagerRow & { manager_id: number };

export default function DashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [selectedManagerId, setSelectedManagerId] = useState<number | null>(null);
  const [routesData, setRoutesData] = useState<AllRoutesResp | null>(null);
  const [routesLoading, setRoutesLoading] = useState(false);
  const [routesError, setRoutesError] = useState("");

  const status = useAsync(() => getStatus(date), [date]);
  const delivery = useAsync(() => getDeliveries(date), [date]);

  const st = status.data;
  const shouldPoll = st?.state === "PREVIEW" || st?.state === "LIVE";
  const est = st ? st.state === "PREVIEW" || Boolean(st.estimated) : false;
  const showProgress = st?.state === "LIVE" || st?.state === "RESULT";
  const internalOn = Boolean(st?.internal?.enabled);

  const rows = delivery.data?.managers ?? [];
  const stops = delivery.data?.stops ?? [];
  const byLineup = delivery.data?.by_lineup ?? {};
  const noData = !status.loading && !delivery.loading && !status.error && !delivery.error && rows.length === 0;

  const managerOptions = useMemo(
    () => rows.filter((x): x is AssignedManager => x.manager_id != null),
    [rows],
  );

  const displayedRoutes = useMemo(() => {
    if (!routesData) return [];
    if (selectedManagerId == null) return routesData.routes;
    return routesData.routes.filter((r) => r.manager_id === selectedManagerId);
  }, [routesData, selectedManagerId]);

  const autoFitKey = `${date}:${selectedManagerId ?? "all"}`;

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
    setSelectedManagerId(null);
    loadRoutes().catch(() => {});
  }, [date]);

  useEffect(() => {
    if (selectedManagerId == null) return;
    const exists = rows.some((m) => m.manager_id === selectedManagerId);
    if (!exists) setSelectedManagerId(null);
  }, [rows, selectedManagerId]);

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
          {st && <Badge state={st.state} />}
          {est && (
            <span style={{ fontSize: 12, color: "#8b8b00", fontWeight: 700 }}>예상치 기준</span>
          )}
          {shouldPoll && (
            <span style={{ fontSize: 12, color: "#c62828", fontWeight: 700 }}>30초 갱신 중</span>
          )}
          <Link to="/settings/internal" style={{ fontSize: 12, color: "#7c3aed", fontWeight: 600 }}>
            직원식 설정
          </Link>          
          <span style={{ marginLeft: "auto", fontSize: 12, color: "#666" }}>
            {st
              ? `주문 마감: ${kstDateTime(st.cutoff_at)} KST${st.cutoff_source === "default" ? " (기본값)" : ""}`
              : ""}
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

      {!error && st && (
        <>
          <StatusCards status={st} />
          <WarningsBar warnings={st.warnings} />
        </>
      )}

      {!error && managerOptions.length > 0 && (
        <div style={{ marginTop: 16, marginBottom: 8, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <label htmlFor="manager-select" style={{ fontSize: 14, fontWeight: 600 }}>노선 강조 매니저</label>
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
        <MapSection
          stops={stops}
          routes={displayedRoutes}
          selectedManagerId={selectedManagerId}
          onSelectManager={setSelectedManagerId}
          autoFitKey={autoFitKey}
        />
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
          <h2 style={{ fontSize: 16, margin: "24px 0 8px" }}>매니저별 현황 {est ? "(예상)" : ""}</h2>
          <ManagerTable rows={rows} stops={stops} showProgress={showProgress} />
        </>
      )}

      {!error && Object.keys(byLineup).length > 0 && (
        <>
          <h2 style={{ fontSize: 16, margin: "24px 0 8px" }}>
            라인업별 {est ? "(예상)" : ""} <span style={{ fontSize: 12, color: "#888", fontWeight: 400 }}>VAT 제외</span>
          </h2>
          <LineupTable byLineup={byLineup} internalOn={internalOn} />
        </>
      )}

      {!error && <InternalBlock internal={st?.internal} est={est} />}
    </PageLayout>
  );
}
