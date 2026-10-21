import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import type { ChipTone } from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import Panel from "@/components/ui/Panel";
import type { ManagerLegs, RouteControl, RouteLegsResp } from "@/api/types";

/* [S3-P2d-4b] 관제: 지연 예상 고객사(전체, 늦은 순) · 노선별 요약 · 노선 상세(배송지별). 화면 조회는 NAVER 호출 없음 */
const hm = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false })
    : "-";
const km = (m: number) => `${(m / 1000).toFixed(1)}km`;
const dur = (ms: number) => {
  const t = Math.round(ms / 60000);
  return t >= 60 ? `${Math.floor(t / 60)}시간 ${t % 60}분` : `${t}분`;
};

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
};

const rowStyle = (on: boolean) => ({ cursor: "pointer", background: on ? "rgba(37, 99, 235, 0.08)" : undefined });

export default function ControlTable({ data, names, selected, onSelect }: Props) {
  const rows = data.managers
    .filter((m): m is Row => Boolean(m.control))
    .sort((a, b) => STATE[a.control.state].rank - STATE[b.control.state].rank || a.manager_id - b.manager_id);
  if (!rows.length) return null;
  const nameOf = (id: number) => names.get(id) ?? `계정 ${id}`;
  const count = (s: RouteControl["state"]) => rows.filter((m) => m.control.state === s).length;
  const lateAll = rows
    .flatMap((m) => m.control.late.map((s) => ({ mid: m.manager_id, s })))
    .sort((a, b) => (b.s.delay_min ?? 0) - (a.s.delay_min ?? 0));
  const sel = rows.find((m) => m.manager_id === selected);

  return (
    <>
      <Panel
        title={lateAll.length ? `지연 예상 고객사 ${lateAll.length}곳` : "지연 예상 고객사 없음"}
        right={<span className="muted small">희망 시각보다 1분 이상 늦게 도착할 것으로 예상되는 곳 · 늦은 순 · 행을 누르면 노선 상세</span>}
      >
        {lateAll.length > 0 && (
          <DataTable columns={["노선", { label: "순서", num: true }, "고객사", "희망", "예상 도착", { label: "지연", num: true }]}>
            {lateAll.map(({ mid, s }) => (
              <tr key={`${mid}:${s.id}`} onClick={() => onSelect(mid)} style={rowStyle(selected === mid)}>
                <td>{nameOf(mid)}</td>
                <td className="num">{s.seq ?? "-"}</td>
                <td>{s.name}</td>
                <td>{hm(s.target_at)}</td>
                <td>{hm(s.eta)}</td>
                <td className="num"><Gap m={s.delay_min} /></td>
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>

      <Panel
        title="노선별 관제"
        right={
          <span className="muted small">
            정체 {count("stalled")} · 지연 예상 {count("late")} · 대기 {count("wait")} · 정상 {count("ok")} · 출발 전 {count("before")} · 완료 {count("done")}
          </span>
        }
        desc={`예상 도착 = 마지막 완료 시각부터 (정차 + 다음 곳 주행)을 앱 배송 순서대로 더한 시각 · 남은 경로는 출발한 노선만 ${data.eta_every_min}분마다 다시 계산 · 정체 = 다음 곳 예상 도착보다 ${data.stall_min}분 넘게 지났는데 새 완료 없음 · 대기 = 정체 조건이지만 지금 출발해도 다음 곳 희망 시각에 맞출 수 있음 · 행을 누르면 지도에서 그 노선만 보고 아래에 배송지별 상세`}
      >
        <DataTable
          columns={[
            "노선", "상태", { label: "완료", num: true }, "마지막 완료", "다음 곳 예상", { label: "남은 거리", num: true },
            { label: "남은 주행 + 정차", num: true }, "예상 완료", { label: "지연 예상", num: true },
            { label: "미지정 고객사", num: true }, { label: "늦게 완료", num: true }, "계산 시각",
          ]}
        >
          {rows.map((m) => {
            const c = m.control;
            const st = STATE[c.state];
            const on = selected === m.manager_id;
            return (
              <tr key={m.manager_id} onClick={() => onSelect(on ? null : m.manager_id)} style={rowStyle(on)}>
                <td>{nameOf(m.manager_id)}</td>
                <td>
                  <Chip tone={st.tone}>{st.label}</Chip>
                  {(c.state === "stalled" || c.state === "wait") && c.behind_min != null && (
                    <span className="muted small"> 예정보다 {c.behind_min}분</span>
                  )}
                </td>
                <td className="num">{c.done}/{c.done + c.remaining}</td>
                <td>{hm(c.last_at)}{c.remaining > 0 && c.idle_min != null ? ` (${c.idle_min}분 전)` : ""}</td>
                <td>{c.remaining ? hm(c.next_eta) : "-"}</td>
                <td className="num">{c.remaining ? km(c.remaining_m) : "-"}</td>
                <td className="num">
                  {c.remaining ? `${dur(c.remaining_drive_ms)} + ${Math.round(c.dwell_min * c.remaining)}분` : "-"}
                </td>
                <td>{c.remaining ? hm(c.finish_at) : "-"}</td>
                <td className="num">{c.late.length ? `${c.late.length}곳 · 최대 ${c.max_delay_min}분` : "-"}</td>
                <td className="num" title={c.no_time.join("\n")}>{c.no_time.length ? `${c.no_time.length}곳` : "-"}</td>
                <td className="num">{c.late_done ? `${c.late_done}곳` : "-"}</td>
                <td className="muted small">
                  {c.remaining
                    ? `${hm(c.calc_at)}${c.uncalc_n ? ` · 미계산 ${c.uncalc_n}곳` : ""}${c.skipped_n ? ` · 연결 불가 ${c.skipped_n}곳` : ""}`
                    : "-"}
                </td>
              </tr>
            );
          })}
        </DataTable>
      </Panel>

      {sel && <RouteDetail m={sel} name={nameOf(sel.manager_id)} onClose={() => onSelect(null)} />}
    </>
  );
}

function RouteDetail({ m, name, onClose }: { m: Row; name: string; onClose: () => void }) {
  const c = m.control;
  const list = [
    ...c.done_stops.map((s) => ({ s, done: true })),
    ...c.stops.map((s) => ({ s, done: false })),
  ];
  return (
    <Panel
      title={`${name} · 배송지별 상세`}
      right={<Button size="sm" onClick={onClose}>닫기</Button>}
      desc={
        c.remaining
          ? `${hm(c.last_at)} 마지막 완료 기준 · 남은 ${c.remaining}곳 ${km(c.remaining_m)} · 주행 ${dur(c.remaining_drive_ms)} + 정차 약 ${c.dwell_min}분/곳 · ${hm(c.calc_at)} 경로 계산 · 남은 곳은 앱 배송 순서대로 간다고 보고 계산`
          : `모두 완료 · 마지막 완료 ${hm(c.last_at)} · 늦게 완료 ${c.late_done}곳`
      }
    >
      <DataTable columns={[{ label: "순서", num: true }, "고객사", "희망", "완료 / 예상 도착", "구분", { label: "희망 대비", num: true }]}>
        {list.map(({ s, done }) => (
          <tr key={`${done ? "d" : "r"}:${s.id}`} className={done ? "muted" : undefined}>
            <td className="num">{s.seq ?? "-"}</td>
            <td>{s.name}</td>
            <td>{hm(s.target_at)}</td>
            <td>{done ? hm(s.done_at) : s.skipped ? "연결 불가" : hm(s.eta)}</td>
            <td>{done ? "완료" : "남음"}</td>
            <td className="num"><Gap m={s.delay_min} done={done} /></td>
          </tr>
        ))}
      </DataTable>
    </Panel>
  );
}
