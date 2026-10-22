import { useEffect, useMemo, useState } from "react";
import PageLayout from "@/layouts/PageLayout";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
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
import ControlTable from "./components/ControlTable";
import MapSection from "@/features/map/MapSection";
import { getStatus } from "@/api/status";
import { getDeliveries } from "@/api/deliveries";
import { getPreviewAll, getRouteLegs, previewRoute, startPreviewAll } from "@/api/routes";
import type { LngLat, PreviewAllStatus, RouteLegsResp, RouteSummary, StopPoint } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { usePolling } from "@/hooks/usePolling";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { todayISO } from "@/lib/date";
import { kstDateTime } from "@/lib/format";
import { useMe } from "@/layouts/shell";


/* [S3-P2d-2b-2] 실제 경로(route_legs) → 지도 형식. 완료 구간 = 실선(completed_path), 미리보기 = 점선(remaining_path) */
const toPts = (p?: LngLat[] | null) =>
  (p ?? []).filter((x) => Array.isArray(x) && x.length >= 2).map(([lng, lat]) => ({ lat, lng }));

function toRoutes(d: RouteLegsResp | null, stops: StopPoint[]): RouteSummary[] {
  if (!d) return [];
  const meta = new Map<number, { name?: string | null; color?: string | null }>();
  for (const s of stops) {
    if (s.manager_id != null && !meta.has(s.manager_id)) meta.set(s.manager_id, { name: s.manager_name, color: s.manager_color });
  }
  return d.managers.map((m) => {
    const done: Array<{ lat: number; lng: number }> = [];
    for (const l of m.legs) {
      const pts = toPts(l.path);
      done.push(...(done.length && pts.length ? pts.slice(1) : pts));   // 구간 끝 = 다음 구간 시작 → 겹치는 점 1개 제외
    }
    return {
      manager_id: m.manager_id,
      manager_name: meta.get(m.manager_id)?.name ?? null,
      manager_color: meta.get(m.manager_id)?.color ?? null,
      mode: m.remaining_stops > 0 ? (m.stops > 0 ? "live" : "preview") : "result",
      completed_path: done,
      remaining_path: toPts(m.preview?.path),
      distance_m: m.distance_m,
      duration_ms: m.duration_ms,
      completed_stops: m.stops,
      remaining_stops: m.remaining_stops,
      toll_fare: 0,
      fuel_price_naver: 0,          // 연비 없으면 NAVER 기본 연비 값 → 지도에서는 표시 안 함 (물류비 화면 참고 칸에서만)
      origin_name: "출발지",
      origin_latitude: d.origin.lat,
      origin_longitude: d.origin.lng,
      source: "cache",
    } as RouteSummary;
  });
}


export default function DashboardPage() {
  const [date, setDate] = useState(todayISO());
  const [selectedManagerId, setSelectedManagerId] = useState<number | null>(null);
  const [routesData, setRoutesData] = useState<RouteLegsResp | null>(null);
  const [pvBusy, setPvBusy] = useState(false);
  const [pvMsg, setPvMsg] = useState("");
  const [routesLoading, setRoutesLoading] = useState(false);
  const [routesError, setRoutesError] = useState("");
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const [focusStop, setFocusStop] = useState<{ id: string; n: number } | null>(null);   // [S3-P2d-5] 관제 → 지도 마커
  const isAdmin = Boolean(useMe()?.is_admin);  
  const auto = useAutoRefresh();

  const status = useAsync(() => getStatus(date), [date]);
  const delivery = useAsync(() => getDeliveries(date), [date]);

  const st = status.data;
  const live = st?.state === "PREVIEW" || st?.state === "LIVE";
  const est = st ? st.state === "PREVIEW" || Boolean(st.estimated) : false;
  const showProgress = st?.state === "LIVE" || st?.state === "RESULT";
  const internalOn = Boolean(st?.internal?.enabled);
  const liveNow = st?.state === "LIVE" && date === todayISO();   // [S3-P2d-5] 지연 예상은 오늘 · 진행 중일 때만

  const rows = delivery.data?.managers ?? [];
  const stops = delivery.data?.stops ?? [];
  const byLineup = delivery.data?.by_lineup ?? {};
  const lineupMeta = useMemo(() => {
    const d = delivery.data;
    if (d?.lineup_meta?.length) return d.lineup_meta;
    return Object.entries(d?.by_lineup ?? {}).map(([id, v]) => ({ id, meal: v.meal, label: v.name }));
  }, [delivery.data]);
  const noData = !status.loading && !delivery.loading && !status.error && !delivery.error && rows.length === 0;
  const mgrNames = useMemo(
    () => new Map(rows.filter((r) => r.manager_id != null).map((r) => [r.manager_id as number, r.manager_name ?? `계정 ${r.manager_id}`])),
    [rows],
  );

  async function loadRoutes() {
    setRoutesLoading(true);
    setRoutesError("");
    try {
      setRoutesData(await getRouteLegs(date));
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
    setFocusStop(null);    
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

  // [S3-P2d-2b-2] 남은 경로 미리보기 (버튼으로만 NAVER 호출, 저장·물류비 반영 안 함)
  const routes = useMemo(() => toRoutes(routesData, stops), [routesData, stops]);
  const pvRows = routesData?.managers.filter((m) => m.remaining_stops > 0) ?? [];
  const pvTarget = selectedManagerId == null ? pvRows : pvRows.filter((m) => m.manager_id === selectedManagerId);
  const pvStale = pvTarget.filter((m) => m.preview_stale).length;

  useEffect(() => { setPvMsg(""); }, [date, selectedManagerId]);

  async function runPreview() {
    setPvBusy(true);
    setPvMsg("");
    try {
      if (selectedManagerId != null) {
        const r = await previewRoute(date, selectedManagerId);
        setPvMsg(r.cached
          ? "바뀐 곳이 없어 이전 계산을 그대로 표시합니다"
          : `계산 완료 · 호출 ${r.calls}회${r.skipped ? ` · ${r.skipped}곳 연결 불가` : ""}`);
      } else {
        let st: PreviewAllStatus = await startPreviewAll(date);
        while (st.status === "running") {
          setPvMsg(`전체 노선 계산 중 ${st.done ?? 0}/${st.total ?? 0}`);
          await new Promise((res) => setTimeout(res, 2000));
          st = await getPreviewAll(date);
        }
        const failed = st.failed?.length ?? 0;
        setPvMsg(`전체 노선 계산 완료 · 호출 ${st.calls ?? 0}회${failed ? ` · 실패 ${failed}개 노선` : ""}`);
      }
      await loadRoutes();
    } catch (e) {
      setPvMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setPvBusy(false);
    }
  }

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

      {!error && stops.length > 0 && routesData && pvTarget.length > 0 && (
        <div className="toolbar" style={{ marginTop: 12, flexWrap: "wrap", rowGap: 8 }}>
          <Button size="sm" variant="primary" disabled={pvBusy || !routesData.enabled} onClick={() => { runPreview().catch(() => {}); }}>
            {pvBusy ? "계산 중…" : selectedManagerId == null ? "전체 노선 남은 경로 미리보기" : "이 노선 남은 경로 미리보기"}
          </Button>
          {pvStale > 0 && <Chip tone="warn">새 완료 반영 필요 {pvStale}개 노선</Chip>}
          <span className="muted small">
            {pvMsg || `실선 = 완료 순서대로 이은 실제 경로 · 점선 = 남은 경로 예상(물류비 미반영) · 오늘 호출 ${routesData.calls_today}/${routesData.daily_limit}`}
          </span>
        </div>
      )}

      {!error && stops.length > 0 && (
        <MapSection
          stops={stops}
          routes={routes}

          state={st?.state}          
          selectedManagerId={selectedManagerId}
          onSelectManager={setSelectedManagerId}
          autoFitKey={`${date}:${selectedManagerId ?? "all"}`}
          loading={delivery.loading}
          routesLoading={routesLoading}
          focusStop={focusStop}
        />        
      )}

      <div id="dash-map-anchor" />
      {!error && routesData && routesData.managers.length > 0 && (
        <ControlTable
          data={routesData}
          names={mgrNames}
          selected={selectedManagerId}
          onSelect={setSelectedManagerId}
          live={liveNow}
          isAdmin={isAdmin}
          onFocusStop={(id) => {
            setFocusStop((p) => ({ id, n: (p?.n ?? 0) + 1 }));
            document.querySelector(".map-box")?.scrollIntoView({ behavior: "smooth", block: "center" });
          }}
          onChanged={() => { void loadRoutes(); }}
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
