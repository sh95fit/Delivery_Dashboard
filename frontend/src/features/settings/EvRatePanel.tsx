import { useCallback, useEffect, useState } from "react";
import Panel from "@/components/ui/Panel";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import DataTable from "@/components/ui/DataTable";
import ErrorBox from "@/components/ui/ErrorBox";
import Modal from "@/components/ui/Modal";
import * as fuel from "@/api/fuel";
import { EV_SPEED_LABEL } from "@/api/fuel";
import type { EvRate, EvRatePreview, EvRateSet, EvSettings, EvSpeed } from "@/api/fuel";
import { errText } from "@/lib/form";
import { kstDateTime } from "@/lib/format";

/* S3-P2g-1 전기차 충전 단가 — 로밍 요금 매트릭스(기후에너지환경부 카드 행) 업로드 · 예상 충전비 기준 설정
   S3-P2g-1d 여러 파일 한 번에 올리기 (최대 5개 · 속도마다 1개 · 하나라도 문제 있으면 전부 저장 안 함) */

type Props = { isAdmin: boolean };
type Row = {
  key: string; file: File; b64: string; prev: EvRatePreview | null; error: string;
  speed: EvSpeed | ""; eff: string;
};

const SPEEDS: EvSpeed[] = ["slow", "mid", "fast50", "fast100", "ultra"];
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_FILES = 5;
const price = (p: number) => p.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
const toB64 = (f: File) =>
  new Promise<string>((ok, ng) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] ?? "");
    r.onerror = () => ng(new Error("파일을 읽지 못했습니다"));
    r.readAsDataURL(f);
  });

export default function EvRatePanel({ isAdmin }: Props) {
  const [sets, setSets] = useState<EvRateSet[] | null>(null);
  const [cfg, setCfg] = useState<EvSettings | null>(null);
  const [speedIn, setSpeedIn] = useState<EvSpeed>("fast50");
  const [kmIn, setKmIn] = useState("2.5");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [effAll, setEffAll] = useState("");
  const [memo, setMemo] = useState("");
  const [peek, setPeek] = useState<string | null>(null);
  const [view, setView] = useState<{ set: EvRateSet; rates: EvRate[] } | null>(null);

  const load = useCallback(async () => {
    const r = await fuel.listEvRates();
    setSets(r.sets);
    setCfg(r.settings);
    setSpeedIn(r.settings.ev_speed);
    setKmIn(String(r.settings.ev_km_per_kwh));
  }, []);

  useEffect(() => {
    load().catch((e) => setError(errText(e)));
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try { await fn(); await load(); return true; } catch (e) { setError(errText(e)); return false; } finally { setBusy(false); }
  }

  function saveSettings() {
    const km = Number(kmIn);
    if (!(km > 0 && km <= 20)) return setError("기본 전비는 0보다 크고 20 이하로 입력하세요 (km/kWh)");
    void run(() => fuel.saveEvSettings({ ev_speed: speedIn, ev_km_per_kwh: km }));
  }

  function openUpload() {
    setError("");
    setRows([]);
    setEffAll("");
    setMemo("");
    setPeek(null);
    setOpen(true);
  }

  function pickFiles(list: FileList | null) {
    setError("");
    setPeek(null);
    const files = Array.from(list ?? []);
    if (files.length > MAX_FILES) {
      setRows([]);
      return setError(`한 번에 ${MAX_FILES}개까지 올릴 수 있습니다 (선택 ${files.length}개)`);
    }
    const big = files.find((f) => f.size > MAX_BYTES);
    if (big) {
      setRows([]);
      return setError(`${big.name}: 파일이 너무 큽니다 (2MB 이하)`);
    }
    setRows(files.map((f, i) => ({ key: `${i}-${f.name}-${f.size}`, file: f, b64: "", prev: null, error: "", speed: "", eff: "" })));
  }

  async function readFiles() {
    if (rows.length === 0) return setError("파일을 선택하세요");
    setBusy(true);
    setError("");
    setPeek(null);
    try {
      const b64s = await Promise.all(rows.map((r) => toB64(r.file)));
      const res = await fuel.previewEvRatesBatch(rows.map((r, i) => ({ file_name: r.file.name, content_b64: b64s[i] ?? "" })));
      setRows(rows.map((r, i) => {
        const p = res[i];
        const b64 = b64s[i] ?? "";
        if (!p || p.error) return { ...r, b64, prev: null, error: p?.error ?? "파일을 읽지 못했습니다", speed: "", eff: "" };
        return { ...r, b64, prev: p, error: "", speed: p.speed ?? "", eff: p.effective_from ?? "" };
      }));
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const setRow = (key: string, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  function issues(r: Row): string[] {
    if (r.error) return [r.error];
    if (!r.prev) return ["미리보기를 누르세요"];
    const out: string[] = [];
    if (!r.speed) out.push("충전 속도를 선택하세요");
    if (!r.eff) out.push("적용 시작일을 입력하세요");
    if (r.speed && rows.filter((o) => !o.error && o.speed === r.speed).length > 1) {
      out.push(`${EV_SPEED_LABEL[r.speed]} 중복 — 속도마다 1개만`);
    }
    if (r.b64 && rows.some((o) => o.key !== r.key && o.b64 === r.b64)) out.push("같은 파일이 2번 선택됨");
    const dup = (sets ?? []).find((s) => s.speed === r.speed && s.effective_from === r.eff);
    if (dup) out.push(`이미 있음 (#${dup.id}) — 목록에서 삭제 후 저장`);
    return out;
  }
  const okCount = rows.filter((r) => issues(r).length === 0).length;
  const ready = rows.length > 0 && okCount === rows.length;
  const read = rows.some((r) => r.prev || r.error);
  const peekRow = rows.find((r) => r.key === peek);
  const peekPrev = peekRow?.prev ?? null;

  function applyEffAll() {
    if (!effAll) return setError("모두 같게 할 적용 시작일을 고르세요");
    setError("");
    setRows((rs) => rs.map((r) => (r.prev ? { ...r, eff: effAll } : r)));
  }

  async function commit() {
    if (!ready) return setError("표의 '확인 필요' 내용을 먼저 해결하세요");
    const items = rows.map((r) => ({
      file_name: r.file.name, content_b64: r.b64, speed: r.speed as EvSpeed, effective_from: r.eff,
      memo: memo.trim() || null,
    }));
    const ok = await run(() => fuel.commitEvRatesBatch(items));
    if (ok) setOpen(false);
  }

  function remove(s: EvRateSet) {
    const msg = `${EV_SPEED_LABEL[s.speed]} ${s.effective_from} 단가(사업자 ${s.rate_count}곳)를 삭제할까요?\n`
      + "물류비 참고 칸의 전기차 예상 충전비가 남은 단가로 다시 계산됩니다.";
    if (!window.confirm(msg)) return;
    void run(() => fuel.deleteEvRates(s.id));
  }

  async function show(s: EvRateSet) {
    setError("");
    try {
      setView({ set: s, rates: await fuel.getEvRates(s.id) });
    } catch (e) {
      setError(errText(e));
    }
  }

  const has = (sp: EvSpeed) => (sets ?? []).some((s) => s.speed === sp);
  const latest = (sp: EvSpeed) =>
    (sets ?? []).filter((s) => s.speed === sp).sort((a, b) => b.effective_from.localeCompare(a.effective_from))[0];

  return (
    <>
      <Panel
        title="전기차 충전 단가 (예상 충전비 기준)"
        right={isAdmin ? <Button size="sm" disabled={busy} onClick={openUpload}>요금 매트릭스 업로드</Button> : undefined}
      >
        {error && !open && <div className="stack"><ErrorBox message={error} /></div>}
        <p className="muted small">
          예상 충전비 = 주행거리 ÷ 전비(차량 연비 칸, 없으면 기본 전비) × 기후에너지환경부 카드로 기후에너지환경부 충전기를 쓸 때 단가.
          물류비 화면의 NCP 예상·오피넷 기준 참고 칸에 같은 값으로 표시하고, 물류비 합계에는 넣지 않습니다.
          실제 비용은 법인카드 결제금액을 주유 기록(전기 차량)으로 입력하면 됩니다.
          전비는 공인 전비가 아니라 냉장·냉난방 등 주행 외 소모를 포함한 실사용 값으로 넣으세요 (기본 2.5km/kWh · 차량 연비 칸에 넣으면 그 값이 우선).
        </p>
        {cfg && (
          <div className="row-gap">
            <span className="small">예상 기준</span>
            <select className="input" value={speedIn} disabled={!isAdmin || busy}
              onChange={(e) => setSpeedIn(e.target.value as EvSpeed)}>
              {SPEEDS.map((s) => <option key={s} value={s}>{EV_SPEED_LABEL[s]}</option>)}
            </select>
            <span className="small">기본 전비</span>
            <input className="input input-sm" inputMode="decimal" value={kmIn} disabled={!isAdmin || busy}
              onChange={(e) => setKmIn(e.target.value)} />
            <span className="small">km/kWh</span>
            {isAdmin && <Button size="sm" variant="primary" disabled={busy} onClick={saveSettings}>저장</Button>}
            {sets && !has(cfg.ev_speed) && (
              <Chip tone="warn">{EV_SPEED_LABEL[cfg.ev_speed]} 단가 없음 · 다른 속도 단가로 대신 계산</Chip>
            )}
          </div>
        )}
        {sets && (
          <div className="row-gap mt">
            {SPEEDS.map((sp) => {
              const cur = latest(sp);
              return (
                <Chip key={sp} tone={cur ? "ok" : "warn"}>
                  {EV_SPEED_LABEL[sp]} {cur ? `${price(cur.base_price)}원 · ${cur.effective_from}부터` : "없음"}
                </Chip>
              );
            })}
          </div>
        )}
        {!sets ? (
          <p className="muted">불러오는 중…</p>
        ) : sets.length === 0 ? (
          <p className="muted mt">올린 요금 매트릭스가 없습니다. 무공해차 누리집에서 속도별 로밍 요금 매트릭스(완속 · 중속 · 급속 50~99kW · 급속 100~199kW · 초급속) 5개를 내려받아 한 번에 선택해 올리세요.</p>
        ) : (
          <div className="mt">
            <DataTable columns={["속도", "적용 시작일", { label: "기준 단가(원/kWh)", num: true }, { label: "사업자", num: true },
              "파일", "올린 사람", "관리"]}>
              {sets.map((s) => (
                <tr key={s.id}>
                  <td>
                    {EV_SPEED_LABEL[s.speed]}
                    {cfg?.ev_speed === s.speed ? <> <Chip tone="ok">예상 기준</Chip></> : null}
                  </td>
                  <td>{s.effective_from}</td>
                  <td className="num">{price(s.base_price)}</td>
                  <td className="num">{s.rate_count}곳</td>
                  <td>{s.file_name ?? "-"}{s.memo ? <span className="muted small"> · {s.memo}</span> : null}</td>
                  <td>{s.created_by ?? "-"} · {kstDateTime(s.created_at)}</td>
                  <td>
                    <div className="row-gap">
                      <Button size="sm" disabled={busy} onClick={() => void show(s)}>보기</Button>
                      {isAdmin && <Button size="sm" variant="danger" disabled={busy} onClick={() => remove(s)}>삭제</Button>}
                    </div>
                  </td>
                </tr>
              ))}
            </DataTable>
          </div>
        )}
      </Panel>

      <Modal
        open={isAdmin && open}
        title={`로밍 요금 매트릭스 업로드 (최대 ${MAX_FILES}개)`}
        onClose={() => setOpen(false)}
        footer={
          <>
            {read && (
              <span className="muted small grow">
                {rows.length}개 중 저장 가능 {okCount}개 · 하나라도 문제가 있으면 아무것도 저장하지 않습니다
              </span>
            )}
            <Button onClick={() => setOpen(false)}>닫기</Button>
            <Button variant="primary" disabled={busy || !ready} onClick={commit}>
              {rows.length > 1 ? `${rows.length}개 저장` : "저장"}
            </Button>
          </>
        }
      >
        {error && <div className="stack"><ErrorBox message={error} /></div>}
        <div className="form-grid">
          <label className="field field-wide">요금 매트릭스 파일 (.xlsx · .xls · 속도별 파일 최대 {MAX_FILES}개 함께 선택)
            <input type="file" className="input" accept=".xls,.xlsx" multiple
              onChange={(e) => pickFiles(e.target.files)} />
          </label>
          <div className="form-actions">
            <Button variant="primary" disabled={busy || rows.length === 0} onClick={readFiles}>
              {busy && !read ? "읽는 중…" : "미리보기"}
            </Button>
          </div>
        </div>
        {read && (
          <>
            <div className="row-gap mt">
              <span className="small">적용 시작일</span>
              <input type="date" className="input" value={effAll} onChange={(e) => setEffAll(e.target.value)} />
              <Button size="sm" onClick={applyEffAll}>모두 같게</Button>
              <span className="small">메모</span>
              <input className="input" value={memo} maxLength={200} placeholder="예: 초기 기준"
                onChange={(e) => setMemo(e.target.value)} />
            </div>
            <p className="muted small">
              속도·적용 시작일은 파일 이름에서 읽었습니다. 파일 이름의 날짜는 내려받은 날이므로 실제 요금 시행일로 고치세요.
              속도마다 1개만 올릴 수 있고, 하나라도 문제가 있으면 아무것도 저장하지 않습니다.
            </p>
            <div className="mt">
              <DataTable columns={["파일", "충전 속도 *", "적용 시작일 *", { label: "기준 단가(원/kWh)", num: true },
                { label: "사업자", num: true }, "판정"]}>
                {rows.map((r) => {
                  const iss = issues(r);
                  return (
                    <tr key={r.key}>
                      <td className="small">{r.file.name}</td>
                      <td>
                        <select className="input" value={r.speed} disabled={!r.prev}
                          onChange={(e) => setRow(r.key, { speed: e.target.value as EvSpeed | "" })}>
                          <option value="">선택</option>
                          {SPEEDS.map((s) => <option key={s} value={s}>{EV_SPEED_LABEL[s]}</option>)}
                        </select>
                      </td>
                      <td>
                        <input type="date" className="input" value={r.eff} disabled={!r.prev}
                          onChange={(e) => setRow(r.key, { eff: e.target.value })} />
                      </td>
                      <td className="num">{r.prev ? price(r.prev.base_price) : "-"}</td>
                      <td className="num">
                        {r.prev
                          ? <Button size="sm" onClick={() => setPeek(peek === r.key ? null : r.key)}>{r.prev.rate_count}곳</Button>
                          : "-"}
                      </td>
                      <td>
                        {iss.length === 0
                          ? <Chip tone="ok">저장 가능</Chip>
                          : iss.map((t) => <div key={t} className="small"><Chip tone="warn">확인 필요</Chip> {t}</div>)}
                      </td>
                    </tr>
                  );
                })}
              </DataTable>
            </div>
            {peekRow && peekPrev && (
              <div className="imp-tbl mt">
                <p className="small"><b>{peekRow.file.name}</b> · {peekPrev.issuer} 카드 · 머리글 {peekPrev.header_row}행 · 단가 없는 칸('-') {peekPrev.skipped}개 제외</p>
                <DataTable columns={["충전 사업자", { label: "원/kWh", num: true }]}>
                  {peekPrev.rates.map((x) => (
                    <tr key={x.operator}>
                      <td>{x.operator}{x.operator === peekPrev.base_operator ? <> <Chip tone="ok">예상 기준</Chip></> : null}</td>
                      <td className="num">{price(x.price)}</td>
                    </tr>
                  ))}
                </DataTable>
              </div>
            )}
          </>
        )}
      </Modal>

      <Modal
        open={view != null}
        title={view ? `${EV_SPEED_LABEL[view.set.speed]} · ${view.set.effective_from} 사업자별 단가 (${view.set.issuer} 카드)` : ""}
        onClose={() => setView(null)}
        footer={<Button onClick={() => setView(null)}>닫기</Button>}
      >
        {view && (
          <div className="imp-tbl">
            <DataTable columns={["충전 사업자", { label: "원/kWh", num: true }]}>
              {view.rates.map((r) => (
                <tr key={r.operator}>
                  <td>{r.operator}</td>
                  <td className="num">{price(r.price)}</td>
                </tr>
              ))}
            </DataTable>
          </div>
        )}
      </Modal>
    </>
  );
}
