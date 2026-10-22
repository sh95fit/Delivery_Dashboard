import { useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import type { ChipTone } from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Panel from "@/components/ui/Panel";
import { addControlExclude, deleteControlExclude } from "@/api/routes";
import type { ControlExclude, ControlStop, ManagerLegs, RouteControl, RouteLegsResp } from "@/api/types";

/* [S3-P2d-5] 관제: 지연 예상 고객사(진행 중일 때만) · 노선별 요약 · 노선 상세(배송지별) · 관제 제외 배송지.
   화면 조회는 NAVER 호출 없음 */
const hm = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false })
    : "-";
const km = (m: number) => `${(m / 1000).toFixed(1)}km`;
const dur = (ms: number) => {
  const t = Math.round(ms / 60000);
  return t >= 60 ? `${Math.floor(t / 60)}시간 ${t % 60}분` : `${t}분`;
};
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const stopMin = (c: RouteControl) => Math.round(c.dwell_min * c.remaining);
const totalMs = (c: RouteControl) => c.remaining_drive_ms + stopMin(c) * 60000;
/* [S3-P2d-5c] 정차 시간: 기본 = 오늘 완료 간격 중앙값, 화면에서 임의 값으로 바꿔 볼 수 있음 */
const DWELL_OPTS = [1, 2, 3, 4, 5, 7, 10, 15];
const LONG_DWELL = 20;      // 이보다 길면 휴식·상차 등으로 보고 강조
const dwellSrc = (c: RouteControl) => (c.dwell_manual ? `임의 설정 · 자동이면 ${c.dwell_auto_min}분` : "오늘 완료 간격 중앙값");

const STATE: Record<RouteControl["state"], { tone: ChipTone; label: string; rank: number }> = {
  stalled: { tone: "warn", label: "정체", rank: 0 },
  late: { tone: "danger", label: "지연 예상", rank: 1 },
  wait: { tone: "caution", label: "대기", rank: 2 },
  ok: { tone: "ok", label: "정상", rank: 3 },
  before: { tone: "neutral", label: "출발 전", rank: 4 },
  incomplete: { tone: "caution", label: "미완료", rank: 5 },
  done: { tone: "neutral", label: "완료", rank: 6 },
};

function Gap({ m, done }: { m: number | null; done?: boolean }) {
  if (m == null) return <span className="muted">-</span>;
  if (m >= 1) return <Chip tone="danger">{done ? `${m}분 늦게 완료` : `${m}분 지연`}</Chip>;
  return <Chip tone="ok">{m <= -1 ? `${-m}분 여유` : "정시"}</Chip>;
}

type Row = ManagerLegs & { control: RouteControl };

type Props = {
  data: RouteLegsResp;
  names: Map<number, string>;
  selected: number | null;
  onSelect: (id: number | null) => void;
  live: boolean;                        // 오늘 · 배송 진행 중(LIVE) → 지연 예상 표시
  isAdmin: boolean;
  onFocusStop: (id: string) => void;    // 배송지 → 지도 마커로 이동
  onChanged: () => void;                // 관제 제외 추가·해제 후 다시 불러오기
  dwellOpt: number | null;              // [S3-P2d-5c] 곳당 정차 임의 설정(분), null = 자동(중앙값)
  onDwell: (v: number | null) => void;
};

const rowStyle = (on: boolean) => ({ cursor: "pointer", background: on ? "rgba(37, 99, 235, 0.08)" : undefined });

export default function ControlTable({ data, names, selected, onSelect, live, isAdmin, onFocusStop, onChanged, dwellOpt, onDwell }: Props) {
  const detailRef = useRef<HTMLDivElement>(null);
  const [jump, setJump] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  // 관제 표에서 노선을 누르면 아래 상세의 맨 위로 스크롤 (지도에서 노선을 고를 때는 스크롤하지 않음)
  useEffect(() => {
    if (jump == null || jump !== selected) return;
    detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setJump(null);
  }, [jump, selected]);

  const rows = data.managers
    .filter((m): m is Row => Boolean(m.control))
    .sort((a, b) => STATE[a.control.state].rank - STATE[b.control.state].rank || a.manager_id - b.manager_id);
  if (!rows.length) return null;
  const nameOf = (id: number) => names.get(id) ?? `계정 ${id}`;
  const count = (s: RouteControl["state"]) => rows.filter((m) => m.control.state === s).length;
  const lateAll = live
    ? rows.flatMap((m) => m.control.late.map((s) => ({ mid: m.manager_id, s })))
        .sort((a, b) => (b.s.delay_min ?? 0) - (a.s.delay_min ?? 0))
    : [];
  const sel = rows.find((m) => m.manager_id === selected);
  const excludes = data.excludes ?? [];
  const open = (id: number) => { onSelect(id); setJump(id); };

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setMsg("");
    try { await fn(); onChanged(); } catch (e) { setMsg(errText(e)); } finally { setBusy(false); }
  }

  function exclude(s: ControlStop) {
    if (s.address_id == null) return;
    const memo = window.prompt(
      `'${s.name}'을(를) 관제에서 제외합니다.\n지도에는 그대로 보이고, 지연 예상·정체·예상 완료·남은 경로에서만 빠집니다 (모든 날짜).\n메모 (선택, 예: 오후 별도 배송)`, "");
    if (memo == null) return;
    run(() => addControlExclude({ address_id: s.address_id as number, label: s.name, memo: memo.trim() || null }));
  }

  function release(x: ControlExclude) {
    if (!window.confirm(`'${x.label ?? x.address_id}' 관제 제외를 해제할까요? 다시 지연 예상·정체 판단에 들어갑니다.`)) return;
    run(() => deleteControlExclude(x.id));
  }

  return (
    <>
      {msg && <div className="stack"><ErrorBox message={msg} /></div>}

      {live && (
        <Panel
          title={lateAll.length ? `지연 예상 고객사 ${lateAll.length}곳` : "지연 예상 고객사 없음"}
          right={<span className="muted small">아직 완료 안 된 곳 중 희망 시각보다 1분 이상 늦게 도착할 것으로 예상되는 곳 · 늦은 순 · 행 = 노선 상세 · 지도 = 마커로 이동</span>}
        >
          {lateAll.length > 0 && (
            <DataTable columns={["노선", { label: "순서", num: true }, "고객사", "희망", "예상 도착", { label: "지연", num: true }, ""]}>
              {lateAll.map(({ mid, s }) => (
                <tr key={`${mid}:${s.id}`} onClick={() => open(mid)} style={rowStyle(selected === mid)}>
                  <td>{nameOf(mid)}</td>
                  <td className="num">{s.seq ?? "-"}</td>
                  <td>{s.name}</td>
                  <td>{hm(s.target_at)}</td>
                  <td>{hm(s.eta)}</td>
                  <td className="num"><Gap m={s.delay_min} /></td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <Button size="sm" variant="ghost" onClick={() => onFocusStop(s.id)}>지도</Button>
                  </td>
                </tr>
              ))}
            </DataTable>
          )}
        </Panel>
      )}

      <Panel
        title="노선별 관제"
        right={
          <>
            <span className="muted small">
              {live
                ? `정체 ${count("stalled")} · 지연 예상 ${count("late")} · 대기 ${count("wait")} · 정상 ${count("ok")} · 출발 전 ${count("before")} · 완료 ${count("done")}`
                : `완료 ${count("done")} · 미완료 ${count("incomplete")}`}
              {excludes.length ? ` · 관제 제외 ${excludes.length}곳` : ""}
            </span>
            {live && (
              <select
                className="input input-sm" value={dwellOpt ?? ""} aria-label="정차 시간"
                title="예상 도착 = 주행 + 곳당 정차. 자동 = 오늘 완료 간격에서 구한 중앙값 (내 화면에만 적용)"
                onChange={(e) => onDwell(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">정차 자동(중앙값)</option>
                {DWELL_OPTS.map((v) => <option key={v} value={v}>정차 {v}분으로 보기</option>)}
              </select>
            )}
          </>
        }
        desc={live
          ? `다음 곳 = 다음 배송지 예상 도착(마우스를 올리면 고객사) · 남은 전체 = 남은 곳을 모두 도는 거리 · 소요(주행 + 정차, 마우스를 올리면 나눠 보기) · 예상 완료 = 마지막 곳 예상 도착 · 남은 경로는 출발한 노선만 ${data.eta_every_min}분마다 다시 계산 · 정체 = 다음 곳 예상 도착보다 ${data.stall_min}분 넘게 지났는데 새 완료 없음 · 대기 = 정체 조건이지만 지금 출발해도 다음 곳 희망 시각에 맞출 수 있음 · 행을 누르면 지도에서 그 노선만 보고 아래 상세로 이동`
          : "지난 날짜·배송 종료 후에는 지연 예상 없이 완료 시각 기준 '늦게 완료'만 봅니다 · 행을 누르면 지도에서 그 노선만 보고 아래 상세로 이동"}
      >
        <DataTable
          columns={[
            "노선", "상태", { label: "완료", num: true }, "마지막 완료", "다음 곳", { label: "남은 전체", num: true },
            "예상 완료", { label: "지연 예상", num: true }, { label: "미지정", num: true }, { label: "늦게 완료", num: true }, "계산",
          ]}
        >
          {rows.map((m) => {
            const c = m.control;
            const st = STATE[c.state];
            const on = selected === m.manager_id;
            const show = live && c.remaining > 0;
            const next = c.stops.find((s) => s.eta && !s.skipped)?.name;
            return (
              <tr key={m.manager_id} onClick={() => (on ? onSelect(null) : open(m.manager_id))} style={rowStyle(on)}>
                <td>{nameOf(m.manager_id)}</td>
                <td>
                  <Chip tone={st.tone}>{st.label}</Chip>
                  {(c.state === "stalled" || c.state === "wait") && c.behind_min != null && (
                    <span className="muted small"> 예정보다 {c.behind_min}분</span>
                  )}
                </td>
                <td className="num">
                  {c.done}/{c.done + c.remaining}
                  {c.excluded?.length ? <span className="muted small"> +제외 {c.excluded.length}</span> : null}
                </td>
                <td>{hm(c.last_at)}{show && c.idle_min != null ? ` (${c.idle_min}분 전)` : ""}</td>
                <td title={show && next ? `다음 곳: ${next}` : undefined}>{show ? hm(c.next_eta) : "-"}</td>
                <td className="num" title={show ? `남은 ${c.remaining}곳 · 주행 ${dur(c.remaining_drive_ms)} + 정차 ${stopMin(c)}분 (곳당 ${c.dwell_min}분, ${dwellSrc(c)})` : undefined}>
                  {show ? `${km(c.remaining_m)} · ${dur(totalMs(c))}` : "-"}
                </td>
                <td>{show ? hm(c.finish_at) : "-"}</td>
                <td className="num">{live && c.late.length ? `${c.late.length}곳 · 최대 ${c.max_delay_min}분` : "-"}</td>
                <td className="num" title={c.no_time.join("\n")}>{c.no_time.length ? `${c.no_time.length}곳` : "-"}</td>
                <td className="num">{c.late_done ? `${c.late_done}곳` : "-"}</td>
                <td className="muted small">
                  {show
                    ? `${hm(c.calc_at)}${c.uncalc_n ? ` · 미계산 ${c.uncalc_n}곳` : ""}${c.skipped_n ? ` · 연결 불가 ${c.skipped_n}곳` : ""}`
                    : "-"}
                </td>
              </tr>
            );
          })}
        </DataTable>
      </Panel>

      {sel && (
        <div ref={detailRef} style={{ scrollMarginTop: 72 }}>
          <RouteDetail
            m={sel} name={nameOf(sel.manager_id)} live={live} isAdmin={isAdmin} busy={busy} excludes={excludes}
            onClose={() => onSelect(null)} onFocus={onFocusStop} onExclude={exclude} onRelease={release}
          />
        </div>
      )}

      {excludes.length > 0 && (
        <Panel
          title={`관제 제외 배송지 ${excludes.length}곳`}
          desc="지도에는 그대로 보이고 지연 예상·정체·예상 완료·남은 경로에서만 빠집니다 (모든 날짜). 노선 상세에서 배송지마다 추가합니다."
        >
          <DataTable columns={["배송지", "메모", "등록", ...(isAdmin ? ["관리"] : [])]}>
            {excludes.map((x) => (
              <tr key={x.id}>
                <td>{x.label ?? `주소ID ${x.address_id}`}</td>
                <td>{x.memo ?? ""}</td>
                <td className="muted small">{x.created_by ?? "-"}</td>
                {isAdmin && (
                  <td><Button size="sm" variant="danger" disabled={busy} onClick={() => release(x)}>해제</Button></td>
                )}
              </tr>
            ))}
          </DataTable>
        </Panel>
      )}
    </>
  );
}

function RouteDetail({ m, name, live, isAdmin, busy, excludes, onClose, onFocus, onExclude, onRelease }: {
  m: Row; name: string; live: boolean; isAdmin: boolean; busy: boolean; excludes: ControlExclude[];
  onClose: () => void; onFocus: (id: string) => void; onExclude: (s: ControlStop) => void; onRelease: (x: ControlExclude) => void;
}) {
  const c = m.control;
  const list = [
    ...c.done_stops.map((s) => ({ s, kind: "done" as const })),
    ...c.stops.map((s) => ({ s, kind: "left" as const })),
    ...(c.excluded ?? []).map((s) => ({ s, kind: "excluded" as const })),
  ];
  const exOf = (s: ControlStop) => excludes.find((x) => x.address_id === s.address_id);
  return (
    <Panel
      title={`${name} · 배송지별 상세`}
      right={<Button size="sm" onClick={onClose}>닫기</Button>}
      desc={
        live && c.remaining
          ? `${hm(c.last_at)} 마지막 완료 기준 · 남은 ${c.remaining}곳 모두 도는 데 ${km(c.remaining_m)} · ${dur(totalMs(c))} (주행 ${dur(c.remaining_drive_ms)} + 정차 ${stopMin(c)}분, 곳당 ${c.dwell_min}분 · ${dwellSrc(c)}) · ${hm(c.calc_at)} 경로 계산 · 남은 곳은 앱 배송 순서대로 간다고 보고 계산 · 정차 = 완료한 곳은 직전 완료부터 걸린 시간 − 주행 시간 · 행을 누르면 지도에서 그 배송지로 이동`
          : `완료 ${c.done}곳 · 마지막 완료 ${hm(c.last_at)} · 늦게 완료 ${c.late_done}곳 · 행을 누르면 지도에서 그 배송지로 이동`
      }
    >
      <DataTable columns={[{ label: "순서", num: true }, "고객사", "희망", "완료 / 예상 도착", "구분", { label: "정차", num: true }, { label: "희망 대비", num: true }, ...(isAdmin ? ["관제"] : [])]}>
        {list.map(({ s, kind }) => {
          const ex = kind === "excluded" ? exOf(s) : undefined;
          return (
            <tr key={`${kind}:${s.id}`} className={kind === "left" ? undefined : "muted"} style={{ cursor: "pointer" }}
              onClick={() => onFocus(s.id)} title="누르면 지도에서 이 배송지로 이동">
              <td className="num">{s.seq ?? "-"}</td>
              <td>{s.name}</td>
              <td>{hm(s.target_at)}</td>
              <td>{kind === "left" ? (s.skipped ? "연결 불가" : live ? hm(s.eta) : "-") : hm(s.done_at)}</td>
              <td>{kind === "done" ? "완료" : kind === "left" ? "남음" : <Chip>관제 제외</Chip>}</td>
              <td className="num">
                {kind === "left"
                  ? <span className="muted">{c.dwell_min}분 (예상)</span>
                  : s.dwell_min == null
                    ? <span className="muted">-</span>
                    : s.dwell_min > LONG_DWELL
                      ? <Chip tone="caution">{Math.round(s.dwell_min)}분 · 긴 정차</Chip>
                      : `${Math.round(s.dwell_min)}분`}
              </td>
              <td className="num">
                {kind === "excluded" || (kind === "left" && !live)
                  ? <span className="muted">-</span>
                  : <Gap m={s.delay_min} done={kind === "done"} />}
              </td>
              {isAdmin && (
                <td onClick={(e) => e.stopPropagation()}>
                  {kind === "excluded"
                    ? ex && <Button size="sm" disabled={busy} onClick={() => onRelease(ex)}>해제</Button>
                    : s.address_id != null && <Button size="sm" variant="ghost" disabled={busy} onClick={() => onExclude(s)}>제외</Button>}
                </td>
              )}
            </tr>
          );
        })}
      </DataTable>
    </Panel>
  );
}
