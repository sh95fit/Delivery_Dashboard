import { useEffect, useMemo, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { getAssignBoard } from "@/api/masters";
import type { AssignBoard, BoardCell, BoardFlag, BoardSpan } from "@/api/masters";
import { errText } from "@/lib/form";
import { todayKst } from "@/lib/format";

/** [S3-P2h-3d-2b] 배정 점검: 배송이 있던 날마다 계정 → 담당 인력 → 차량 (물류비와 같은 판정, 읽기 전용) */
const SRC_LABEL: Record<string, string> = { chosen: "담당 지정", log: "근무 기록", fixed: "고정 계정" };
const SRC_MARK: Record<string, string> = { chosen: "지", log: "기" };

function shiftMonth(ym: string, n: number): string {
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1 + n, 1)).toISOString().slice(0, 7);
}

function weekday(ym: string, day: number): number {
  return new Date(`${ym}-${String(day).padStart(2, "0")}T00:00:00Z`).getUTCDay();
}

function carText(c: BoardCell): string {
  if (c.plate_no) return c.plate_no.replace(/\D/g, "").slice(-4);
  if (c.basis === "own") return "개인";
  if (c.basis === "unknown") return "?";
  return "없음";
}

function cellTitle(day: number, c: BoardCell, labels: Record<BoardFlag, string>): string {
  const lines = [
    `${day}일`,
    `담당: ${c.worker_name ?? "없음"}${c.src ? ` (${SRC_LABEL[c.src]})` : ""}`,
    `차량: ${c.plate_no ?? (c.basis === "own" ? "개인 차량" : c.basis === "unknown" ? "이력 없음" : "차량 없음")}`,
  ];
  if (c.flags.length) lines.push(`표시: ${c.flags.map((f) => labels[f]).join(", ")}`);
  return lines.join("\n");
}

function spanText(s: BoardSpan): string {
  return `${s.name ?? `인력 ${s.worker_id}`} · ${s.start ?? "?"} ~ ${s.end ?? "계속"}`;
}

export default function AssignBoardTab() {
  const [month, setMonth] = useState(() => todayKst().slice(0, 7));
  const [data, setData] = useState<AssignBoard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [onlyBad, setOnlyBad] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    getAssignBoard(month)
      .then((r) => { if (alive) setData(r); })
      .catch((e) => { if (alive) { setData(null); setError(errText(e)); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [month]);

  const days = useMemo(() => (data ? Array.from({ length: data.last_day }, (_, i) => i + 1) : []), [data]);
  const rows = useMemo(() => {
    if (!data) return [];
    return onlyBad ? data.rows.filter((r) => data.errors.some((f) => r.counts[f] > 0)) : data.rows;
  }, [data, onlyBad]);
  const flagKeys = data ? (Object.keys(data.flags) as BoardFlag[]) : [];
  const isErr = (f: BoardFlag) => Boolean(data && data.errors.includes(f));
  const badCount = (counts: Record<BoardFlag, number>) => (data ? data.errors.reduce((n, f) => n + (counts[f] ?? 0), 0) : 0);

  return (
    <>
      <Panel
        title="배정 점검 (계정 → 담당 인력 → 차량)"
        right={
          <div className="row-gap">
            <Button size="sm" onClick={() => setMonth((m) => shiftMonth(m, -1))}>이전 달</Button>
            <input type="month" className="input input-sm" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
            <Button size="sm" onClick={() => setMonth((m) => shiftMonth(m, 1))}>다음 달</Button>
            <label className="check"><input type="checkbox" checked={onlyBad} onChange={(e) => setOnlyBad(e.target.checked)} />고칠 칸 있는 계정만</label>
          </div>
        }
      >
        <p className="small muted mb">
          물류비·유류비와 같은 판정입니다. 배송이 있던 날만 표시합니다. 빨간 칸은 고쳐야 하는 칸입니다 —
          담당 인력 없음: 인력 › 고정 계정 또는 근무 기록 · 퇴사 뒤 운행: 퇴사일 또는 다음 담당자의 계정 이력 ·
          차량 이력 없음: 인력 › 차량 이용 · 처분 뒤 사용: 차량 처분일 또는 차량 이용 이력. 주황 칸(공유 차량)은 확인용입니다.
        </p>
        {error && <div className="stack"><ErrorBox message={error} /></div>}
        {loading && <Spinner />}
        {!loading && data && (
          <>
            <div className="ab-legend">
              {flagKeys.map((f) => (
                <Chip key={f} tone={data.totals[f] ? (isErr(f) ? "danger" : "caution") : "neutral"}>{data.flags[f]} {data.totals[f]}</Chip>
              ))}
              <span className="small muted">칸: 담당자 / 차량 끝 4자리 · <b>지</b> 담당 지정 · <b>기</b> 근무 기록 · 표시 없음 = 고정 계정</span>
            </div>
            {rows.length === 0 ? (
              <div className="muted small">{data.rows.length ? "이 달에 고칠 칸이 없습니다." : "이 달에 배송 기록이 없습니다."}</div>
            ) : (
              <div className="tbl-wrap">
                <table className="tbl wl-month ab-tbl">
                  <thead>
                    <tr>
                      <th className="wl-name">계정</th>
                      {days.map((d) => {
                        const w = weekday(data.month, d);
                        return <th key={d} className={w === 0 ? "wl-sun" : w === 6 ? "wl-sat" : undefined}>{d}</th>;
                      })}
                      <th className="num">운행</th>
                      <th className="num">고칠 칸</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.manager_id}>
                        <td className="wl-name"><span className="dot" style={{ background: r.color ?? "#9ca3af" }} />{r.name}</td>
                        {days.map((d) => {
                          const c = r.cells[String(d)];
                          if (!c) return <td key={d} className="ab-day ab-off">·</td>;
                          const bad = c.flags.some((f) => isErr(f));
                          const cls = bad ? "ab-cell ab-bad" : c.flags.includes("shared") ? "ab-cell ab-shared" : "ab-cell";
                          return (
                            <td key={d} className="ab-day">
                              <div className={cls} title={cellTitle(d, c, data.flags)}>
                                <b>{c.worker_name ?? "담당 없음"}{c.src && SRC_MARK[c.src] ? <sup>{SRC_MARK[c.src]}</sup> : null}</b>
                                <span className="ab-car">{carText(c)}</span>
                              </div>
                            </td>
                          );
                        })}
                        <td className="num">{r.run_days}</td>
                        <td className="num">{badCount(r.counts) || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Panel>

      {!loading && data && (
        <Panel title={`이력 겹침 ${data.overlaps.length}건 · 안 쓴 차량 ${data.unused_vehicles.length}대`}>
          {data.overlaps.length === 0 ? (
            <div className="muted small">계정·차량 이력 겹침이 없습니다 (달과 상관없이 전체 기준).</div>
          ) : (
            <DataTable columns={["구분", "대상", "앞 이력", "뒤 이력", "겹침 시작"]}>
              {data.overlaps.map((o, i) => (
                <tr key={`${o.kind}-${o.value}-${i}`}>
                  <td>{o.kind === "account" ? "계정" : "차량"}</td>
                  <td>{o.label}</td>
                  <td>{spanText(o.first)}</td>
                  <td>{spanText(o.second)}</td>
                  <td>{o.from ?? "-"}</td>
                </tr>
              ))}
            </DataTable>
          )}
          <p className="small muted mt">
            이 달 배송에 안 쓴 사용 중 차량: {data.unused_vehicles.length ? data.unused_vehicles.join(", ") : "없음"}
          </p>
        </Panel>
      )}
    </>
  );
}
