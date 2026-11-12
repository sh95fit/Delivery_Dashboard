import { useEffect, useMemo, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Spinner from "@/components/ui/Spinner";
import { addBoardExclude, deleteBoardExclude, getAssignBoard } from "@/api/masters";
import type { AssignBoard, BoardCell, BoardExclude, BoardFlag, BoardSpan, ExcludeReason } from "@/api/masters";
import { errText } from "@/lib/form";
import { todayKst } from "@/lib/format";

/** [S3-P2h-3d-2b] 배정 점검: 배송이 있던 날마다 계정 → 담당 인력 → 차량 (물류비와 같은 판정, 읽기 전용)
 *  [S3-P2h-3d-5] 점검 제외 계정: 고칠 칸 수에서 빼고 회색으로 표시 (인센티브·물류비 계산은 그대로) */
const SRC_LABEL: Record<string, string> = { chosen: "담당 지정", log: "근무 기록", fixed: "고정 계정" };
const SRC_MARK: Record<string, string> = { chosen: "지", log: "기" };
const REASONS: ExcludeReason[] = ["internal", "hold", "other"];
type XForm = { mid: string; reason: ExcludeReason; start: string; end: string; memo: string };

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
  if (c.ex) lines.push(`점검 제외: ${c.ex} (고칠 칸 수에서 뺌)`);
  return lines.join("\n");
}

function spanText(s: BoardSpan): string {
  return `${s.name ?? `인력 ${s.worker_id}`} · ${s.start ?? "?"} ~ ${s.end ?? "계속"}`;
}

function exText(x: BoardExclude): string {
  return `${x.start_date} ~ ${x.end_date ?? "계속"}`;
}

export default function AssignBoardTab({ isAdmin }: { isAdmin: boolean }) {
  const [month, setMonth] = useState(() => todayKst().slice(0, 7));
  const [data, setData] = useState<AssignBoard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [onlyBad, setOnlyBad] = useState(false);
  const [tick, setTick] = useState(0);
  const [xf, setXf] = useState<XForm | null>(null);
  const [xErr, setXErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    getAssignBoard(month)
      .then((r) => { if (alive) setData(r); })
      .catch((e) => { if (alive) { setData(null); setError(errText(e)); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [month, tick]);

  const days = useMemo(() => (data ? Array.from({ length: data.last_day }, (_, i) => i + 1) : []), [data]);
  const rows = useMemo(() => {
    if (!data) return [];
    return onlyBad ? data.rows.filter((r) => data.errors.some((f) => r.counts[f] > 0)) : data.rows;
  }, [data, onlyBad]);
  const flagKeys = data ? (Object.keys(data.flags) as BoardFlag[]) : [];
  const isErr = (f: BoardFlag) => Boolean(data && data.errors.includes(f));
  const badCount = (counts: Record<BoardFlag, number>) => (data ? data.errors.reduce((n, f) => n + (counts[f] ?? 0), 0) : 0);

  function openForm() {
    setXErr("");
    setXf({ mid: "", reason: "internal", start: `${month}-01`, end: "", memo: "" });
  }

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setXErr("");
    try { await fn(); setXf(null); setTick((t) => t + 1); } catch (e) { setXErr(errText(e)); } finally { setBusy(false); }
  }

  function saveExclude() {
    if (!xf) return;
    if (!xf.mid) return setXErr("계정을 고르세요");
    if (!xf.start) return setXErr("시작일을 넣으세요");
    if (xf.end && xf.end < xf.start) return setXErr("종료일이 시작일보다 빠릅니다");
    run(() => addBoardExclude({ manager_id: Number(xf.mid), reason: xf.reason, start_date: xf.start,
      end_date: xf.end || null, memo: xf.memo.trim() || null }));
  }

  function removeExclude(x: BoardExclude) {
    if (!window.confirm(`${x.name} 점검 제외(${x.reason_label} · ${exText(x)})를 해제할까요?\n해제하면 그 기간의 빈 칸이 다시 고칠 칸으로 셉니다.`)) return;
    run(() => deleteBoardExclude(x.id));
  }

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
          회색 칸은 점검 제외 계정(직원식·보류 등)이라 고칠 칸 수에서 뺍니다.
        </p>
        {error && <div className="stack"><ErrorBox message={error} /></div>}
        {loading && <Spinner />}
        {!loading && data && (
          <>
            <div className="ab-legend">
              {flagKeys.map((f) => (
                <Chip key={f} tone={data.totals[f] ? (isErr(f) ? "danger" : "caution") : "neutral"}>{data.flags[f]} {data.totals[f]}</Chip>
              ))}
              {data.excluded > 0 && <Chip>점검 제외 {data.excluded}</Chip>}
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
                          const err = c.flags.some((f) => isErr(f));
                          const bad = err && !c.ex;
                          const cls = bad ? "ab-cell ab-bad" : err ? "ab-cell ab-ex" : c.flags.includes("shared") ? "ab-cell ab-shared" : "ab-cell";
                          return (
                            <td key={d} className="ab-day">
                              <div className={cls} title={cellTitle(d, c, data.flags)}>
                                <b>{c.worker_name ?? (c.ex ? `제외(${c.ex})` : "담당 없음")}{c.src && SRC_MARK[c.src] ? <sup>{SRC_MARK[c.src]}</sup> : null}</b>
                                <span className="ab-car">{carText(c)}</span>
                              </div>
                            </td>
                          );
                        })}
                        <td className="num">{r.run_days}</td>
                        <td className="num">{badCount(r.counts) || (r.ex_days ? <span className="muted">제외 {r.ex_days}</span> : "-")}</td>
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
        <Panel
          title={`점검 제외 계정 ${data.excludes.length}건`}
          right={isAdmin && <Button size="sm" variant="primary" onClick={openForm}>제외 추가</Button>}
        >
          <p className="small muted mb">
            일부러 담당을 비워 둔 계정(직원식·보류 등)은 고칠 칸 수에서 뺍니다. 표시만 바뀌고 인센티브·물류비 계산은 그대로입니다.
            종료일을 넣으면 다음 날부터 다시 점검합니다.
          </p>
          {xErr && !xf && <div className="stack"><ErrorBox message={xErr} /></div>}
          {xf && (
            <div className="ed-form">
              {xErr && <div className="stack"><ErrorBox message={xErr} /></div>}
              <div className="form-grid">
                <label className="field">계정 *
                  <select className="input" value={xf.mid} onChange={(e) => setXf({ ...xf, mid: e.target.value })}>
                    <option value="">선택</option>
                    {data.rows.map((r) => <option key={r.manager_id} value={r.manager_id}>{r.name}</option>)}
                  </select>
                </label>
                <label className="field">사유
                  <select className="input" value={xf.reason} onChange={(e) => setXf({ ...xf, reason: e.target.value as ExcludeReason })}>
                    {REASONS.map((k) => <option key={k} value={k}>{data.exclude_reasons[k]}</option>)}
                  </select>
                </label>
                <label className="field">시작일 *<input type="date" className="input" value={xf.start} onChange={(e) => setXf({ ...xf, start: e.target.value })} /></label>
                <label className="field">종료일 (비우면 계속)<input type="date" className="input" value={xf.end} onChange={(e) => setXf({ ...xf, end: e.target.value })} /></label>
                <label className="field field-wide">메모<input className="input" value={xf.memo} maxLength={200} onChange={(e) => setXf({ ...xf, memo: e.target.value })} /></label>
                <div className="form-actions">
                  <Button onClick={() => setXf(null)}>취소</Button>
                  <Button variant="primary" disabled={busy} onClick={saveExclude}>저장</Button>
                </div>
              </div>
            </div>
          )}
          {data.excludes.length === 0 ? (
            <div className="muted small">점검 제외 계정이 없습니다.</div>
          ) : (
            <DataTable columns={["계정", "사유", "기간", "메모", "등록", ...(isAdmin ? ["관리"] : [])]}>
              {data.excludes.map((x) => (
                <tr key={x.id}>
                  <td>{x.name}</td>
                  <td><Chip>{x.reason_label}</Chip></td>
                  <td>{exText(x)}</td>
                  <td>{x.memo ?? "-"}</td>
                  <td className="small muted">{x.created_by ?? "-"}</td>
                  {isAdmin && <td><Button size="sm" variant="danger" disabled={busy} onClick={() => removeExclude(x)}>해제</Button></td>}
                </tr>
              ))}
            </DataTable>
          )}
        </Panel>
      )}

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
