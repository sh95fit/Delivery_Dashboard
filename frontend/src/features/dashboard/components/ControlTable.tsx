import Chip from "@/components/ui/Chip";
import type { ChipTone } from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import Panel from "@/components/ui/Panel";
import type { ManagerLegs, RouteControl, RouteLegsResp } from "@/api/types";

/* [S3-P2d-4] 노선별 관제 — 남은 거리·예상 완료·지연 예상·정체 (화면 조회는 NAVER 호출 없음) */
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
  ok: { tone: "ok", label: "정상", rank: 2 },
  before: { tone: "neutral", label: "출발 전", rank: 3 },
  incomplete: { tone: "caution", label: "미완료", rank: 4 },
  done: { tone: "neutral", label: "완료", rank: 5 },
};

type Row = ManagerLegs & { control: RouteControl };

type Props = {
  data: RouteLegsResp;
  names: Map<number, string>;
  selected: number | null;
  onSelect: (id: number | null) => void;
};

export default function ControlTable({ data, names, selected, onSelect }: Props) {
  const rows = data.managers
    .filter((m): m is Row => Boolean(m.control))
    .sort((a, b) => STATE[a.control.state].rank - STATE[b.control.state].rank || a.manager_id - b.manager_id);
  if (!rows.length) return null;
  const count = (s: RouteControl["state"]) => rows.filter((m) => m.control.state === s).length;

  return (
    <Panel
      title="노선별 관제"
      right={
        <span className="muted small">
          정체 {count("stalled")} · 지연 예상 {count("late")} · 정상 {count("ok")} · 출발 전 {count("before")} · 완료 {count("done")}
        </span>
      }
      desc={`예상 완료 = 마지막 완료 시각 + 정차(그날 평균) + 남은 경로 주행 시간 · 남은 경로는 출발한 노선만 ${data.eta_every_min}분마다 다시 계산 · 정체 = ${data.stall_min}분 이상 새 완료 없음 · 희망 시각이 없는 곳은 지연 판단에서 빼고 '미지정 고객사'로 표시 · 행을 누르면 지도에서 그 노선만 보기`}
    >
      <DataTable
        columns={[
          "노선", "상태", { label: "완료", num: true }, "마지막 완료", { label: "남은 거리", num: true },
          { label: "남은 주행", num: true }, "예상 완료", { label: "지연 예상", num: true },
          { label: "미지정 고객사", num: true }, { label: "늦게 완료", num: true }, "계산 시각",
        ]}
      >
        {rows.map((m) => {
          const c = m.control;
          const st = STATE[c.state];
          const sel = selected === m.manager_id;
          return (
            <tr
              key={m.manager_id}
              onClick={() => onSelect(sel ? null : m.manager_id)}
              style={{ cursor: "pointer", background: sel ? "rgba(37, 99, 235, 0.08)" : undefined }}
            >
              <td>{names.get(m.manager_id) ?? `계정 ${m.manager_id}`}</td>
              <td><Chip tone={st.tone}>{st.label}</Chip></td>
              <td className="num">{c.done}/{c.done + c.remaining}</td>
              <td>{hm(c.last_at)}{c.remaining > 0 && c.idle_min != null ? ` (${c.idle_min}분 전)` : ""}</td>
              <td className="num">{c.remaining ? km(c.remaining_m) : "-"}</td>
              <td className="num">{c.remaining ? dur(c.remaining_drive_ms) : "-"}</td>
              <td>{c.remaining ? hm(c.finish_at) : "-"}</td>
              <td className="num" title={c.late.map((x) => `${x.name}: 희망 ${hm(x.target_at)} → 예상 ${hm(x.eta)}`).join("\n")}>
                {c.late.length ? `${c.late.length}곳` : "-"}
              </td>
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
  );
}
