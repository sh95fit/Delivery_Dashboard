import { useEffect, useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Badge from "@/components/ui/Badge";
import Chip from "@/components/ui/Chip";
import Panel from "@/components/ui/Panel";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import EmptyState from "@/components/ui/EmptyState";
import RetryButton from "@/components/ui/RetryButton";
import RefreshControl from "@/components/ui/RefreshControl";
import StatusCards from "./components/StatusCards";
import ManagerTable from "./components/ManagerTable";
import WarningsBar from "./components/WarningsBar";
import LineupTable from "./components/LineupTable";
import InternalBlock from "./components/InternalBlock";
import MapSection from "@/features/map/MapSection";
import { getStatus } from "@/api/status";
import { getDeliveries } from "@/api/deliveries";
import { getAllRoutes } from "@/api/routes";
import type { AllRoutesResp } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { usePolling } from "@/hooks/usePolling";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { todayISO } from "@/lib/date";
import { kstDateTime } from "@/lib/format";


export default function DashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [selectedManagerId, setSelectedManagerId] = useState<number | null>(null);
  const [routesData, setRoutesData] = useState<AllRoutesResp | null>(null);
  const [routesLoading, setRoutesLoading] = useState(false);
  const [routesError, setRoutesError] = useState("");
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const auto = useAutoRefresh();

  const status = useAsync(() => getStatus(date), [date]);
  const delivery = useAsync(() => getDeliveries(date), [date]);

  const st = status.data;
  const live = st?.state === "PREVIEW" || st?.state === "LIVE";
  const est = st ? st.state === "PREVIEW" || Boolean(st.estimated) : false;
  const showProgress = st?.state === "LIVE" || st?.state === "RESULT";
  const internalOn = Boolean(st?.internal?.enabled);

  const rows = delivery.data?.managers ?? [];
  const stops = delivery.data?.stops ?? [];
  const byLineup = delivery.data?.by_lineup ?? {};
  const lineupMeta = delivery.data?.lineup_meta ?? [];
  const noData = !status.loading && !delivery.loading && !status.error && !delivery.error && rows.length === 0;

  async function loadRoutes() {
    setRoutesLoading(true);
    setRoutesError("");
    try {
      setRoutesData(await getAllRoutes(date));
    } catch (e) {
      setRoutesError(e instanceof Error ? e.message : String(e));
      setRoutesData(null);
    } finally {
      setRoutesLoading(false);
    }
  }

  const refreshAll = () => {
    status.refetch().catch(() => {});
    delivery.refetch().catch(() => {});
    loadRoutes().catch(() => {});
  };

  useEffect(() => {
    setSelectedManagerId(null);
    loadRoutes().catch(() => {});
  }, [date]);

  useEffect(() => {
    if (status.data) setLastAt(new Date());
  }, [status.data]);

  useEffect(() => {
    if (selectedManagerId == null) return;
    if (!rows.some((m) => m.manager_id === selectedManagerId)) setSelectedManagerId(null);
  }, [rows, selectedManagerId]);

  // 자동 갱신: 오늘·진행 중 날짜 + 사용자가 켠 경우에만
  usePolling(refreshAll, auto.sec * 1000, Boolean(live) && auto.on);

  const busy = status.loading || delivery.loading || routesLoading;
  const error = status.error || delivery.error || routesError;

  return (
    <PageLayout
      title="배송 대시보드"
      right={
        <>
          <div className="toolbar">
            <input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
            {st && <Badge state={st.state} />}
            {est && <Chip tone="warn">예상치 기준</Chip>}
          </div>
          <div className="toolbar toolbar-end">
            {st && (
              <span className="muted small">
                주문 마감 {kstDateTime(st.cutoff_at)} KST{st.cutoff_source === "default" ? " (기본값)" : ""}
              </span>
            )}
            <RefreshControl
              live={Boolean(live)} on={auto.on} sec={auto.sec} busy={busy} lastAt={lastAt}
              onToggle={auto.setOn} onSec={auto.setSec} onRefresh={refreshAll}
            />
          </div>
        </>
      }
    >
      {error && (
        <div className="stack">
          <ErrorBox message={error} />
          <div><RetryButton onClick={refreshAll} /></div>
        </div>
      )}

      {busy && !st && <Spinner />}

      {!error && st && (
        <>
          <StatusCards status={st} />
          <WarningsBar warnings={st.warnings} />
        </>
      )}

      {!error && stops.length > 0 && (
        <MapSection
          stops={stops}
          routes={routesData?.routes ?? []}
          state={st?.state}          
          selectedManagerId={selectedManagerId}
          onSelectManager={setSelectedManagerId}
          autoFitKey={`${date}:${selectedManagerId ?? "all"}`}
          loading={delivery.loading}
          routesLoading={routesLoading}
        />
      )}

      {!error && noData && (
        <EmptyState
          title="해당 날짜 데이터가 없습니다"
          description="주문/배송 데이터가 없는 날짜이거나 아직 집계되지 않았습니다."
        />
      )}

      {!error && rows.length > 0 && (
        <Panel
          title={`매니저별 현황${est ? " (예상)" : ""}`}
          right={<span className="muted small">금액 VAT 제외{internalOn ? " · 직원식 금액 제외" : ""}</span>}
        >
          <ManagerTable rows={rows} stops={stops} showProgress={showProgress} meta={lineupMeta} />
        </Panel>
      )}

      {!error && Object.keys(byLineup).length > 0 && (
        <Panel title={`라인업별${est ? " (예상)" : ""}`} right={<span className="muted small">VAT 제외</span>}>
          <LineupTable byLineup={byLineup} internalOn={internalOn} order={lineupMeta.map((m) => m.id)} />
        </Panel>
      )}

      {!error && <InternalBlock internal={st?.internal} est={est} />}
    </PageLayout>
  );
}
