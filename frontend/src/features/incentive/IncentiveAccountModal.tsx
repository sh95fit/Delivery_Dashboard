import { useEffect, useMemo, useRef, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import { getIncDay, saveIncAccountsMonth } from "@/api/incentive";
import type { Band, IncDayView, IncMonthPerson } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num, todayKst } from "@/lib/format";
import IncentiveDetailModal from "./IncentiveDetailModal";
import IncentiveOwnerModal from "./IncentiveOwnerModal";
import { STATUS, amt, previewDay, wd } from "./util";

type Props = {
  month: string; lastDay: number; person: IncMonthPerson; closed: boolean; isAdmin: boolean;
  focusDay: number | null;          // 월 보드에서 누른 날짜 (이름으로 열면 null)
  rates: Record<string, Band[]>;    // [S2-P4c-3c] 단가표 id → 고객사 구간 (입력 미리보기)
  onClose: () => void; onChanged: () => void;   // onChanged: 월 보드 다시 불러오기 (창은 유지)
};
const str = (v: number | null) => (v == null ? "" : String(v));
const MAX = 500;   // 서버 AccountDayItem le=500

/** [S2-P4c-3] 한 계정의 한 달 고객사 수 입력 (근무표 월 표 한 달 입력과 같은 방식)
 *  [S2-P4c-3b] [상세]로 제외·조정·미지급·특수 수당·담당 변경까지 이 창에서 처리
 *  [S2-P4c-3c] 입력 즉시 데일리·합계·상태 미리보기, [저장하고 닫기] */
export default function IncentiveAccountModal({ month, lastDay, person, closed, isAdmin, focusDay, rates, onClose, onChanged }: Props) {
  const today = todayKst();
  const iso = (d: number) => `${month}-${String(d).padStart(2, "0")}`;
  const days = useMemo(() => Array.from({ length: lastDay }, (_, i) => i + 1)
    .filter((d) => person.days[String(d)]), [lastDay, person]);
  const [forms, setForms] = useState<Record<number, string>>(() =>
    Object.fromEntries(days.map((d) => [d, str(person.days[String(d)].accounts)])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [detail, setDetail] = useState<IncDayView | null>(null);
  const [opening, setOpening] = useState<number | null>(null);
  const [ownerOpen, setOwnerOpen] = useState(false);
  const refs = useRef<Record<number, HTMLInputElement | null>>({});
  const rowRefs = useRef<Record<number, HTMLTableRowElement | null>>({});

  const rows = days.map((d) => {
    const c = person.days[String(d)];
    const future = iso(d) > today;
    const lock = !isAdmin || closed || future || c.stops === 0;
    const f = forms[d] ?? str(c.accounts);
    const bad = f !== "" && (!/^\d{1,3}$/.test(f) || Number(f) > MAX);
    const chg = !lock && f !== str(c.accounts);
    const pv = chg && !bad
      ? previewDay(c, f === "" ? null : Number(f), c.rate_id == null ? null : rates[String(c.rate_id)])
      : null;
    return { d, c, f, future, lock, bad, dirty: chg, pv };
  });
  const dirty = rows.filter((r) => r.dirty);
  const bad = dirty.filter((r) => r.bad);
  const empty = rows.filter((r) => !r.lock && r.f === "");
  const sumNow = rows.reduce((a, r) => a + r.c.total, 0);
  const sumNew = rows.reduce((a, r) => a + (r.pv ? r.pv.total : r.c.total), 0);

  /* 월 보드에서 날짜 칸으로 열었으면 그 날짜 행으로 이동 */
  useEffect(() => {
    if (focusDay == null) return;
    const t = setTimeout(() => {
      rowRefs.current[focusDay]?.scrollIntoView({ block: "center" });
      const el = refs.current[focusDay];
      if (el && !el.disabled) { el.focus(); el.select(); }
    }, 0);
    return () => clearTimeout(t);
  }, []);

  function next(i: number) {
    for (let k = i + 1; k < rows.length; k++) {
      const el = refs.current[rows[k].d];
      if (el && !el.disabled) { el.focus(); el.select(); return; }
    }
  }
  function fill() {
    setForms((s) => {
      const n = { ...s };
      for (const r of empty) if (r.c.order_accounts > 0) n[r.d] = String(r.c.order_accounts);
      return n;
    });
  }
  function leave(fn: () => void) {
    if (dirty.length > 0 && !confirm(`저장하지 않은 고객사 수 ${dirty.length}일이 있습니다. 취소하고 닫을까요?`)) return;
    fn();
  }

  /** close=true: 저장 성공 후 창 닫기 */
  async function save(close: boolean) {
    if (dirty.length === 0 || bad.length > 0) return;
    const cleared = dirty.filter((r) => r.f === "");
    if (cleared.length && !confirm(
      `고객사 수를 지우는 날 ${cleared.length}일: ${cleared.map((r) => `${r.d}일`).join(", ")}\n` +
      "지우면 그날 인센티브가 '고객사 수 입력 필요'로 바뀝니다. 계속할까요?")) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      const r = await saveIncAccountsMonth(person.manager_id,
        dirty.map((x) => ({ work_date: iso(x.d), value: x.f === "" ? null : Number(x.f) })));
      onChanged();
      if (close) { onClose(); return; }
      setNote(`고객사 수 저장 ${num(r.saved)}일` +
        `${r.cleared ? ` · 지움 ${num(r.cleared)}일` : ""}${r.unchanged ? ` · 기존과 같아 건너뜀 ${num(r.unchanged)}일` : ""}`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  /* ---- [S2-P4c-3b] 상세 (일자별 입력과 같은 상세 창을 이 창 위에 띄움) ---- */
  async function fetchDay(d: string): Promise<IncDayView | null> {
    const v = await getIncDay(d);
    if (!v.items.some((x) => x.manager_id === person.manager_id)) {
      setError(`${d}: 이 계정의 그날 정보를 찾지 못했습니다 (새로고침하세요)`);
      return null;
    }
    return v;
  }
  async function openDetail(day: number) {
    setOpening(day);
    setError("");
    try {
      const v = await fetchDay(iso(day));
      if (v) setDetail(v);
    } catch (e) {
      setError(errText(e));
    } finally {
      setOpening(null);
    }
  }
  /** 상세에서 저장하면: 상세 다시 불러오기 + 월 보드 다시 불러오기 (입력 중인 고객사 수는 유지) */
  async function detailChanged() {
    if (detail) {
      try {
        setDetail(await fetchDay(detail.date));
      } catch (e) {
        setError(errText(e));
      }
    }
    onChanged();
  }
  const dRow = detail?.items.find((x) => x.manager_id === person.manager_id) ?? null;
  const dLocked = !isAdmin || !detail || detail.closed || detail.future;
  const ownerLocked = !isAdmin || !detail || detail.closed;
  const saveOff = closed || busy || dirty.length === 0 || bad.length > 0;

  const pending = rows.filter((r) => !r.future && r.c.stops > 0 && r.c.accounts == null).length;
  return (
    <Modal open size="lg" onClose={() => leave(onClose)}
      title={<>{person.manager_name} · {Number(month.slice(5))}월 인센티브</>}
      footer={<>
        <span className="muted small grow">
          배송일 {num(rows.filter((r) => r.c.stops > 0).length)}일 · 입력 필요 {num(pending)}일 · 변경 {num(dirty.length)}일
          {" · "}월 합계 {num(sumNow)}원
          {dirty.length > 0 && sumNew !== sumNow && <b className="inc-pv"> → {num(sumNew)}원 (저장 전)</b>}
        </span>
        <Button onClick={() => leave(onClose)}>닫기</Button>
        {isAdmin && (
          <>
            <Button onClick={() => save(false)} disabled={saveOff}>
              {busy ? "저장 중…" : `${num(dirty.length)}일 저장 (계속 입력)`}
            </Button>
            <Button variant="primary" onClick={() => save(true)} disabled={saveOff}>
              {busy ? "저장 중…" : "저장하고 닫기"}
            </Button>
          </>
        )}
      </>}
    >
      {error && <ErrorBox message={error} />}
      {note && <div className="notice">✓ {note}</div>}
      {closed && <Chip tone="warn">마감된 달 · 수정 불가 (근무 기록 › 월 표 › 마감 관리에서 해제)</Chip>}
      {bad.length > 0 && <div className="wl-block">고객사 수는 0~{MAX} 숫자로 입력하세요: {bad.map((r) => `${r.d}일`).join(", ")}</div>}
      <div className="bo-tools">
        {isAdmin && !closed && (
          <Button size="sm" variant="ghost" onClick={fill} disabled={empty.length === 0}>
            빈 칸에 주문 고객사 수 채우기 ({num(empty.length)})
          </Button>
        )}
        <span className="muted small">
          고객사 수(수거 포함)를 입력하고 Enter로 다음 날로 넘어갑니다. 입력하면 데일리·합계·상태가 바로 계산됩니다
          (<span className="inc-pv">파란 기울임</span> = 저장 전 미리보기 · 최대 구간 초과 같은 경고는 저장 후 표시).
          배송지 제외·제품 수 조정·미지급·특수 수당·담당 변경은 그 날짜의 [상세]에서 이 창을 벗어나지 않고 처리합니다
          (상세 변경은 바로 저장되고, 입력 중인 고객사 수는 그대로 남습니다).
        </span>
      </div>
      <div className="ia-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>날짜</th><th className="num">배송지</th><th className="num">제품 수</th>
              <th className="num">주문 고객사(참고)</th><th>고객사 수</th>
              <th className="num">데일리</th><th className="num">특수 수당</th><th className="num">합계</th>
              <th>상태</th><th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const cls = [r.c.stops === 0 || r.future ? "off" : "", r.d === focusDay ? "ia-focus" : ""].filter(Boolean).join(" ");
              const st = r.pv ? r.pv.status : r.c.status;
              return (
                <tr key={r.d} className={cls || undefined} ref={(el) => { rowRefs.current[r.d] = el; }}>
                  <td>{r.d}일 ({wd(iso(r.d))})</td>
                  <td className="num">{num(r.c.stops)}</td>
                  <td className="num">{num(r.c.product_total)}</td>
                  <td className="num inc-ref">{num(r.c.order_accounts)}</td>
                  <td>
                    {r.c.stops > 0 ? (
                      <input className={`input input-sm inc-acc${r.bad ? " bad" : r.dirty ? " dirty" : ""}`} inputMode="numeric"
                        value={r.f} placeholder={r.future ? "예정" : "입력"} disabled={r.lock}
                        ref={(el) => { refs.current[r.d] = el; }}
                        onChange={(e) => setForms((s) => ({ ...s, [r.d]: e.target.value.trim() }))}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); next(i); } }} />
                    ) : <span className="muted small">배송 없음</span>}
                  </td>
                  <td className="num">
                    {r.pv ? <span className="inc-pv" title="저장 전 미리보기">{amt(r.pv.payable)}</span>
                      : r.c.payable == null ? "-" : num(r.c.payable)}
                  </td>
                  <td className="num">{r.c.extras ? num(r.c.extras) : "-"}</td>
                  <td className="num">
                    <b className={r.pv ? "inc-pv" : undefined}>{num(r.pv ? r.pv.total : r.c.total)}</b>
                  </td>
                  <td>
                    {r.future ? <Chip tone="neutral">예정</Chip> : <Chip tone={STATUS[st][1]}>{STATUS[st][0]}</Chip>}
                    {r.dirty && <Chip tone="neutral">저장 전</Chip>}
                    {!r.pv && r.c.warns.length > 0 && <span className="inc-warn" title={r.c.warns.join("\n")}>⚠{r.c.warns.length}</span>}
                  </td>
                  <td>
                    <Button size="sm" disabled={opening != null} onClick={() => openDetail(r.d)}>
                      {opening === r.d ? "여는 중…" : "상세"}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {detail && dRow && (
        <IncentiveDetailModal row={dRow} view={detail} locked={dLocked}
          onClose={() => { setDetail(null); setOwnerOpen(false); }} onChanged={detailChanged}
          onOwner={ownerLocked ? undefined : () => setOwnerOpen(true)} />
      )}
      {ownerOpen && detail && dRow && (
        <IncentiveOwnerModal row={dRow} view={detail}
          onClose={() => setOwnerOpen(false)} onSaved={() => { void detailChanged(); }} />
      )}
    </Modal>
  );
}
