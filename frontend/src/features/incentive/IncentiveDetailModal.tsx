import { useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import { addExclusion, addExtra, addHold, addQtyAdj, deleteExclusion, deleteExtra, deleteQtyAdj, releaseHold, updateExtra } from "@/api/incentive";
import type { ExcludeReason, IncDayRow, IncDayView } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num } from "@/lib/format";
import { STATUS, parseAmt, signed, wonOr } from "./util";

type Props = { row: IncDayRow; view: IncDayView; locked: boolean; onClose: () => void; onChanged: () => Promise<void> };
type ExForm = { aid: number; reason: ExcludeReason | ""; memo: string };
type AForm = { lineup: string; qty: string; reason: string };          // lineup "total" = 제품 총량
type XForm = { item: string; unit: string; qty: string; memo: string };
type EditForm = { id: number; unit: string; qty: string; memo: string };
const BIG = 100_000;
const EMPTY_A: AForm = { lineup: "total", qty: "", reason: "" };
const EMPTY_X: XForm = { item: "", unit: "", qty: "1", memo: "" };
const lineupKey = (pid: number | null) => (pid == null ? "total" : String(pid));

/** 건수 1~50 */
function parseQty(s: string): number | null {
  const t = s.trim();
  if (!/^\d{1,2}$/.test(t)) return null;
  const n = Number(t);
  return n >= 1 && n <= 50 ? n : null;
}
/** 조정 수량 ±1~2000 (0 제외) */
function parseDelta(s: string): number | null {
  const t = s.replace(/\s/g, "");
  if (!/^[-+]?\d{1,4}$/.test(t)) return null;
  const n = Number(t);
  return n === 0 || Math.abs(n) > 2000 ? null : n;
}

export default function IncentiveDetailModal({ row, view, locked, onClose, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [ex, setEx] = useState<ExForm | null>(null);
  const [af, setAf] = useState<AForm>(EMPTY_A);
  const [holdReason, setHoldReason] = useState("");
  const [xf, setXf] = useState<XForm>(EMPTY_X);
  const [edit, setEdit] = useState<EditForm | null>(null);

  const aQty = parseDelta(af.qty);
  const xItem = view.extra_items.find((i) => String(i.id) === xf.item) ?? null;
  const xUnit = parseAmt(xf.unit);
  const xQty = parseQty(xf.qty);
  const xTotal = xUnit != null && xQty != null ? xUnit * xQty : null;
  const xDiff = xItem?.unit_amount != null && xUnit != null && xUnit !== xItem.unit_amount;
  const xSame = xItem ? row.extra_list.filter((x) => x.item_id === xItem.id).length : 0;
  const eRow = edit ? row.extra_list.find((x) => x.id === edit.id) ?? null : null;
  const eUnit = edit ? parseAmt(edit.unit) : null;
  const eQty = edit ? parseQty(edit.qty) : null;
  const eTotal = eUnit != null && eQty != null ? eUnit * eQty : null;
  const pending = !!ex || !!edit || xf.item !== "" || af.qty !== "" || af.reason.trim() !== "" || holdReason.trim() !== "";

  function close() {
    if (pending && !confirm("저장하지 않은 입력이 있습니다. 닫을까요?")) return;
    onClose();
  }
  async function run(fn: () => Promise<unknown>, done: string): Promise<boolean> {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const r = await fn();
      await onChanged();
      const w = (r as { warns?: string[] } | null)?.warns ?? [];
      setMsg(`✓ ${done}${w.length ? ` · ⚠ ${w.join(" / ")}` : ""}`);
      return true;
    } catch (e) {
      setError(errText(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  /* ---- ① 배송지 제외 ---- */
  async function saveEx() {
    if (!ex || !ex.reason) return;
    const f = ex;
    if (await run(() => addExclusion({ work_date: view.date, manager_id: row.manager_id, address_id: f.aid,
      reason: f.reason as ExcludeReason, memo: f.memo.trim() || null }), "배송지 제외")) setEx(null);
  }
  async function undoEx(id: number, name: string) {
    if (!confirm(`'${name}' 제외를 해제할까요? (수량이 다시 집계됩니다)`)) return;
    await run(() => deleteExclusion(id), "제외 해제");
  }

  /* ---- ② 제품 수 조정 목록 ---- */
  async function addAdj() {
    const reason = af.reason.trim();
    if (aQty == null || !reason) return;
    const pid = af.lineup === "total" ? null : Number(af.lineup);
    const label = view.adj_lineups.find((l) => lineupKey(l.product_id) === af.lineup)?.label ?? "제품 총량";
    const q = aQty;
    if (await run(() => addQtyAdj({ work_date: view.date, manager_id: row.manager_id, product_id: pid, qty: q, reason }),
      `${label} ${signed(q)} 조정 추가`)) setAf({ ...EMPTY_A, lineup: af.lineup });
  }
  async function removeAdj(id: number, label: string, qty: number) {
    const r = prompt(`'${label} ${signed(qty)}' 조정을 삭제합니다. 삭제 사유를 입력하세요`)?.trim();
    if (!r) return;
    await run(() => deleteQtyAdj(id, r), "조정 삭제");
  }

  /* ---- ③ 미지급 ---- */
  async function hold() {
    const r = holdReason.trim();
    if (!r) return;
    if (!confirm(`${row.manager_name} · ${view.date} 데일리 인센티브를 미지급 처리할까요?\n사유: ${r}\n(특수 수당은 그대로 지급)`)) return;
    if (await run(() => addHold(view.date, row.manager_id, r), "미지급 등록")) setHoldReason("");
  }
  async function release(id: number) {
    const r = prompt("미지급 해제 사유를 입력하세요")?.trim();
    if (!r) return;
    await run(() => releaseHold(id, r), "미지급 해제");
  }

  /* ---- ④ 특수 수당 (단가 × 건수) ---- */
  function pickItem(id: string) {
    const it = view.extra_items.find((i) => String(i.id) === id);
    setXf({ ...xf, item: id, unit: it?.unit_amount ? String(it.unit_amount) : "" });
  }
  async function addX() {
    if (!xItem || xUnit == null || xQty == null || xTotal == null) return;
    const item = xItem, unit = xUnit, qty = xQty, total = xTotal;
    const memo = xf.memo.trim();
    const lines = [`${row.manager_name} · ${view.date}`,
      `${item.name}  ${num(unit)}원 × ${qty}건 = ${num(total)}원${memo ? ` (${memo})` : ""}`];
    if (xDiff) lines.push(`⚠ 기본 단가 ${num(item.unit_amount)}원과 다릅니다`);
    if (xSame) lines.push(`⚠ 같은 품목이 이미 ${xSame}줄 있습니다 (중복 입력이 아닌지 확인)`);
    if (total >= BIG) lines.push(`⚠ ${num(BIG)}원 이상입니다. 금액을 다시 확인하세요`);
    if (!confirm(`${lines.join("\n")}\n\n특수 수당으로 추가할까요?`)) return;
    if (await run(() => addExtra({ work_date: view.date, manager_id: row.manager_id, item_id: item.id, qty,
      unit_amount: unit, memo: memo || null }), `${item.name} ${num(total)}원 추가`)) setXf(EMPTY_X);
  }
  async function saveEdit() {
    if (!edit || !eRow || eUnit == null || eQty == null || eTotal == null) return;
    const id = edit.id, memo = edit.memo.trim(), unit = eUnit, qty = eQty;
    if (!confirm(`${eRow.item_name}\n${num(eRow.unit_amount)}원 × ${eRow.qty}건 = ${num(eRow.amount)}원\n→ ${num(unit)}원 × ${qty}건 = ${num(eTotal)}원\n\n수정할까요?`
      + (eTotal >= BIG ? `\n\n⚠ ${num(BIG)}원 이상입니다.` : ""))) return;
    if (await run(() => updateExtra(id, { qty, unit_amount: unit, memo: memo || null }), "특수 수당 수정")) setEdit(null);
  }
  async function removeX(id: number, name: string) {
    const r = prompt(`'${name}' 특수 수당 삭제 사유를 입력하세요`)?.trim();
    if (!r) return;
    await run(() => deleteExtra(id, r), "특수 수당 삭제");
  }

  const reasons = Object.entries(view.exclude_reasons) as Array<[ExcludeReason, string]>;
  const xHints: string[] = [];
  if (xf.unit !== "" && xUnit == null) xHints.push("단가는 1원~100만 원 숫자로 입력하세요");
  if (xf.qty !== "" && xQty == null) xHints.push("건수는 1~50");
  if (xDiff) xHints.push(`기본 단가 ${num(xItem?.unit_amount)}원과 다릅니다`);
  if (xSame) xHints.push(`같은 품목이 이미 ${xSame}줄 있습니다`);

  return (
    <Modal open size="xl" title={`${row.manager_name} · ${view.date} 인센티브 상세`} onClose={close}
      footer={<Button onClick={close}>닫기</Button>}>
      {locked && <div className="wl-block">{view.closed ? "마감된 달입니다" : view.future ? "미래 날짜입니다" : "관리자만 수정할 수 있습니다"} — 조회만 가능</div>}
      {error && <ErrorBox message={error} />}
      {msg && <div className="notice">{msg}</div>}

      <div className="inc-calc">
        <table className="tbl inc-mini inc-lu">
          <thead><tr><th>제품 수</th><th className="num">자동</th><th className="num">제외</th><th className="num">조정</th><th className="num">반영</th></tr></thead>
          <tbody>
            {row.lineups.map((l) => (
              <tr key={l.product_id}>
                <td>{l.label}</td>
                <td className="num">{num(l.auto)}</td>
                <td className="num">{l.excluded ? `−${num(l.excluded)}` : "-"}</td>
                <td className="num">{l.adjust ? signed(l.adjust) : "-"}</td>
                <td className="num">{num(l.final)}</td>
              </tr>
            ))}
            {row.adj_total !== 0 && (
              <tr><td>제품 총량 조정</td><td /><td /><td className="num">{signed(row.adj_total)}</td><td className="num">{signed(row.adj_total)}</td></tr>
            )}
            <tr className="sum">
              <td>합계</td>
              <td className="num">{num(row.auto_qty)}</td>
              <td className="num">{row.excluded_qty ? `−${num(row.excluded_qty)}` : "-"}</td>
              <td className="num">{row.delta ? signed(row.delta) : "-"}</td>
              <td className="num">{num(row.product_total)}</td>
            </tr>
          </tbody>
        </table>
        <div>
          제품 인센티브 = {wonOr(row.product_incentive)}
          {row.product_unit ? <span className="inc-ref"> (초과분 × {num(row.product_unit)}원)</span> : null}
        </div>
        <div>
          고객사 수 = {row.accounts == null
            ? <><Chip tone="caution">입력 필요</Chip><span className="inc-ref"> 일자별 입력 표의 '고객사 수' 칸에 입력하세요</span></>
            : <><b>{num(row.accounts)}</b> → {wonOr(row.account_incentive)}
                {row.account_unit ? <span className="inc-ref"> (초과분 × {num(row.account_unit)}원)</span> : null}</>}
          <span className="inc-ref"> · 참고: 배송지 {num(row.stops)} · 주문 고객사 {num(row.order_accounts)}</span>
        </div>
        <div className="inc-ref">참고(집계 제외): 석식 {num(row.dinner_qty)} · 파일럿 가정식 {num(row.pilot_qty)}</div>
        <div className="inc-calc-sum">
          데일리 인센티브 {row.held ? <><s>{wonOr(row.incentive)}</s> 0원 (미지급)</>
            : row.payable == null ? <span className="inc-ref">보류</span> : `${num(row.payable)}원`}
          {" + "}특수 수당 {num(row.extras)}원 = <b>{num(row.total)}원</b>{" "}
          <Chip tone={STATUS[row.status][1]}>{STATUS[row.status][0]}</Chip>
        </div>
        {row.warns.map((w) => <div key={w} className="wl-warn">⚠ {w}</div>)}
      </div>

      <section className="inc-sec">
        <h3>① 배송지별 수량 · 제외</h3>
        <p className="hint">퀵 발송·다른 매니저 처리·미배송처럼 이 매니저가 처리하지 않은 배송지는 [제외]하세요. 그 배송지의 가정식·밀 수량이 전부 빠집니다.</p>
        <table className="tbl inc-mini">
          <thead><tr><th>배송지</th><th className="num">가정식</th><th className="num">프레시</th><th className="num">라이트</th>
            <th className="num">석식·파일럿</th><th className="num">주문 고객사</th><th>상태</th><th /></tr></thead>
          <tbody>
            {row.stop_list.map((s) => {
              const x = s.exclusion;
              const name = s.address_name ?? `배송지 ${s.address_id}`;
              return (
                <tr key={s.address_id} className={x ? "excluded" : undefined}>
                  <td>{name}{s.shared && !x && <Chip tone="caution" title="같은 날 다른 계정에도 배정됨">함께 배정</Chip>}</td>
                  <td className="num">{num(s.gajung_qty)}</td>
                  <td className="num">{num(s.fresh_qty)}</td>
                  <td className="num">{num(s.light_qty)}</td>
                  <td className="num inc-ref">{num(s.dinner_qty)} · {num(s.pilot_qty)}</td>
                  <td className="num">{num(s.order_accounts)}</td>
                  <td className="keep">
                    {x ? <Chip tone="warn" title={`${x.created_by ?? ""} ${x.memo ?? ""}`}>제외 · {x.reason_label}</Chip>
                      : ex?.aid === s.address_id ? (
                        <span className="inc-row">
                          <select className="input input-sm" value={ex.reason}
                            onChange={(e) => setEx({ ...ex, reason: e.target.value as ExcludeReason | "" })}>
                            <option value="">사유 선택</option>
                            {reasons.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                          </select>
                          <input className="input input-sm" placeholder="메모 (선택)" maxLength={200} value={ex.memo}
                            onChange={(e) => setEx({ ...ex, memo: e.target.value })} />
                        </span>
                      ) : "집계"}
                  </td>
                  <td className="keep">
                    {locked ? null : x ? (
                      <Button size="sm" disabled={busy} onClick={() => undoEx(x.id, name)}>제외 해제</Button>
                    ) : ex?.aid === s.address_id ? (
                      <span className="inc-row">
                        <Button size="sm" variant="primary" disabled={busy || !ex.reason} onClick={saveEx}>제외 저장</Button>
                        <Button size="sm" variant="ghost" onClick={() => setEx(null)}>취소</Button>
                      </span>
                    ) : (
                      <Button size="sm" disabled={busy || !!ex} onClick={() => setEx({ aid: s.address_id, reason: "", memo: "" })}>제외</Button>
                    )}
                  </td>
                </tr>
              );
            })}
            {row.stop_list.length === 0 && <tr><td colSpan={8} className="muted small">배정된 배송지가 없습니다.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="inc-sec">
        <h3>② 제품 수 조정 (목록)</h3>
        <p className="hint">배송지 하나가 통째로 빠지면 ①의 [제외]를 쓰세요. 일부 수량만 다를 때 라인업 또는 제품 총량으로 ± 수량을 한 줄씩 추가합니다. 모든 줄의 합이 제품 수에 반영되고, 잘못 넣은 줄은 [삭제]하세요 (이력은 남습니다).</p>
        {row.adj_list.length > 0 && (
          <table className="tbl inc-mini">
            <thead><tr><th>구분</th><th className="num">수량</th><th>사유</th><th>입력</th><th /></tr></thead>
            <tbody>
              {row.adj_list.map((a) => (
                <tr key={a.id}>
                  <td>{a.label}</td>
                  <td className="num"><b>{signed(a.qty)}</b></td>
                  <td>{a.reason}</td>
                  <td className="inc-ref">{a.created_by}</td>
                  <td>{!locked && <Button size="sm" variant="ghost" disabled={busy} onClick={() => removeAdj(a.id, a.label, a.qty)}>삭제</Button>}</td>
                </tr>
              ))}
              <tr className="sum"><td>조정 합계</td><td className="num">{signed(row.adj_list.reduce((s, a) => s + a.qty, 0))}</td><td colSpan={3} /></tr>
            </tbody>
          </table>
        )}
        {!locked && (
          <div className="inc-xform inc-aform">
            <label className="inc-f">구분
              <select className="input input-sm" value={af.lineup} onChange={(e) => setAf({ ...af, lineup: e.target.value })}>
                {view.adj_lineups.map((l) => <option key={lineupKey(l.product_id)} value={lineupKey(l.product_id)}>{l.label}</option>)}
              </select>
            </label>
            <label className="inc-f">수량 (±)
              <input className="input input-sm" inputMode="numeric" placeholder="예: -3" value={af.qty}
                onChange={(e) => setAf({ ...af, qty: e.target.value.trim() })} />
            </label>
            <label className="inc-f">사유(필수)
              <input className="input input-sm inc-f-wide" maxLength={200} placeholder="예: 퀵으로 3개 발송" value={af.reason}
                onChange={(e) => setAf({ ...af, reason: e.target.value })}
                onKeyDown={(e) => { if (e.key === "Enter") addAdj(); }} />
            </label>
            <Button size="sm" variant="primary" disabled={busy || aQty == null || !af.reason.trim()} onClick={addAdj}>조정 추가</Button>
            {af.qty !== "" && aQty == null && <div className="inc-xhint">⚠ 수량은 0이 아닌 정수(±2000 이내)로 입력하세요</div>}
          </div>
        )}
      </section>

      <section className="inc-sec">
        <h3>③ 미지급 (데일리 인센티브만)</h3>
        <p className="hint">과실이 1건이라도 남아 있으면 그날 제품·고객사 인센티브가 0원이 됩니다. 특수 수당에는 영향이 없습니다.</p>
        {row.hold_list.map((h) => (
          <div key={h.id} className="inc-row">
            <Chip tone="danger">미지급</Chip> {h.reason} <span className="inc-ref">{h.created_by}</span>
            {!locked && <Button size="sm" disabled={busy} onClick={() => release(h.id)}>해제</Button>}
          </div>
        ))}
        {!locked && (
          <div className="inc-row mt">
            <input className="input input-sm inc-f-wide" placeholder="과실 사유 (필수, 예: 배송 지연 30분)"
              maxLength={200} value={holdReason} onChange={(e) => setHoldReason(e.target.value)} />
            <Button size="sm" variant="danger" disabled={busy || !holdReason.trim()} onClick={hold}>미지급 등록</Button>
          </div>
        )}
      </section>

      <section className="inc-sec">
        <h3>④ 특수 수당 (인센티브와 별도 · 추가 지급)</h3>
        <p className="hint">수당 = 단가 × 건수. 고정 금액 품목은 단가가 자동으로 채워지고, 수시 입력 품목은 단가를 직접 입력합니다.</p>
        {row.extra_list.length > 0 && (
          <table className="tbl inc-mini">
            <thead><tr><th>품목</th><th className="num">단가</th><th className="num">건수</th><th className="num">수당</th><th>비고</th><th>입력</th><th /></tr></thead>
            <tbody>
              {row.extra_list.map((x) => edit?.id === x.id ? (
                <tr key={x.id} className="ed-editing">
                  <td>{x.item_name}</td>
                  <td className="num"><input className="input input-sm inc-n" inputMode="numeric" value={edit.unit}
                    onChange={(e) => setEdit({ ...edit, unit: e.target.value })} /></td>
                  <td className="num"><input className="input input-sm inc-n-sm" inputMode="numeric" value={edit.qty}
                    onChange={(e) => setEdit({ ...edit, qty: e.target.value.trim() })} /></td>
                  <td className="num"><b>{eTotal == null ? "확인" : num(eTotal)}</b></td>
                  <td><input className="input input-sm" maxLength={200} value={edit.memo}
                    onChange={(e) => setEdit({ ...edit, memo: e.target.value })} /></td>
                  <td />
                  <td className="inc-row">
                    <Button size="sm" variant="primary" disabled={busy || eTotal == null} onClick={saveEdit}>저장</Button>
                    <Button size="sm" variant="ghost" onClick={() => setEdit(null)}>취소</Button>
                  </td>
                </tr>
              ) : (
                <tr key={x.id}>
                  <td>{x.item_name}</td>
                  <td className="num">{num(x.unit_amount)}</td>
                  <td className="num">{x.qty}</td>
                  <td className="num"><b>{num(x.amount)}</b></td>
                  <td>{x.memo ?? ""}</td>
                  <td className="inc-ref">{x.created_by}</td>
                  <td className="inc-row">
                    {!locked && <>
                      <Button size="sm" disabled={busy || !!edit}
                        onClick={() => setEdit({ id: x.id, unit: String(x.unit_amount), qty: String(x.qty), memo: x.memo ?? "" })}>수정</Button>
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => removeX(x.id, x.item_name)}>삭제</Button>
                    </>}
                  </td>
                </tr>
              ))}
              <tr className="sum"><td>합계</td><td /><td /><td className="num">{num(row.extras)}</td><td colSpan={3} /></tr>
            </tbody>
          </table>
        )}
        {!locked && view.extra_items.length > 0 && (
          <div className="inc-xform">
            <label className="inc-f">품목
              <select className="input input-sm" value={xf.item} onChange={(e) => pickItem(e.target.value)}>
                <option value="">선택</option>
                {view.extra_items.map((i) => (
                  <option key={i.id} value={i.id}>{i.name} · {i.unit_amount ? `${num(i.unit_amount)}원 고정` : "수시 입력"}</option>
                ))}
              </select>
            </label>
            <label className="inc-f">단가 (원)
              <input className="input input-sm inc-n" inputMode="numeric" placeholder={xItem?.unit_amount ? "" : "직접 입력"}
                value={xf.unit} onChange={(e) => setXf({ ...xf, unit: e.target.value })} />
            </label>
            <span className="inc-op">×</span>
            <label className="inc-f">건수
              <input className="input input-sm inc-n-sm" inputMode="numeric" value={xf.qty}
                onChange={(e) => setXf({ ...xf, qty: e.target.value.trim() })} />
            </label>
            <span className="inc-op">=</span>
            <div className="inc-f">수당<b className="inc-total-amt">{xTotal == null ? "-" : `${num(xTotal)}원`}</b></div>
            <label className="inc-f">비고 (선택)
              <input className="input input-sm inc-f-wide" maxLength={200} placeholder="예: 2곳 수거" value={xf.memo}
                onChange={(e) => setXf({ ...xf, memo: e.target.value })} />
            </label>
            <Button size="sm" variant="primary" disabled={busy || !xItem || xTotal == null} onClick={addX}>특수 수당 추가</Button>
            {xHints.length > 0 && <div className="inc-xhint">⚠ {xHints.join(" · ")}</div>}
          </div>
        )}
        {view.extra_items.length === 0 && <div className="muted small">사용 중인 품목이 없습니다 (단가표·품목 탭에서 추가)</div>}
      </section>
    </Modal>
  );
}