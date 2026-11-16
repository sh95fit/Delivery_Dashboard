import { useMemo, useRef, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import Chip from "@/components/ui/Chip";
import ErrorBox from "@/components/ui/ErrorBox";
import { saveIncAccountsMonth } from "@/api/incentive";
import type { IncMonthPerson } from "@/api/incentive";
import { errText } from "@/lib/form";
import { num, todayKst } from "@/lib/format";
import { STATUS, wd } from "./util";

type Props = {
  month: string; lastDay: number; person: IncMonthPerson; closed: boolean; isAdmin: boolean;
  onClose: () => void; onSaved: (msg: string) => void; onPick: (d: string) => void;
};
const str = (v: number | null) => (v == null ? "" : String(v));
const MAX = 500;   // 서버 AccountDayItem le=500

/** [S2-P4c-3] 한 계정의 한 달 고객사 수 입력 (근무표 월 표 한 달 입력과 같은 방식) */
export default function IncentiveAccountModal({ month, lastDay, person, closed, isAdmin, onClose, onSaved, onPick }: Props) {
  const today = todayKst();
  const iso = (d: number) => `${month}-${String(d).padStart(2, "0")}`;
  const days = useMemo(() => Array.from({ length: lastDay }, (_, i) => i + 1)
    .filter((d) => person.days[String(d)]), [lastDay, person]);
  const [forms, setForms] = useState<Record<number, string>>(() =>
    Object.fromEntries(days.map((d) => [d, str(person.days[String(d)].accounts)])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refs = useRef<Record<number, HTMLInputElement | null>>({});

  const rows = days.map((d) => {
    const c = person.days[String(d)];
    const future = iso(d) > today;
    const lock = !isAdmin || closed || future || c.stops === 0;
    const f = forms[d] ?? str(c.accounts);
    const bad = f !== "" && (!/^\d{1,3}$/.test(f) || Number(f) > MAX);
    return { d, c, f, future, lock, bad, dirty: !lock && f !== str(c.accounts) };
  });
  const dirty = rows.filter((r) => r.dirty);
  const bad = dirty.filter((r) => r.bad);
  const empty = rows.filter((r) => !r.lock && r.f === "");

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

  async function save() {
    if (dirty.length === 0 || bad.length > 0) return;
    const cleared = dirty.filter((r) => r.f === "");
    if (cleared.length && !confirm(
      `고객사 수를 지우는 날 ${cleared.length}일: ${cleared.map((r) => `${r.d}일`).join(", ")}\n` +
      "지우면 그날 인센티브가 '고객사 수 입력 필요'로 바뀝니다. 계속할까요?")) return;
    setBusy(true);
    setError("");
    try {
      const r = await saveIncAccountsMonth(person.manager_id,
        dirty.map((x) => ({ work_date: iso(x.d), value: x.f === "" ? null : Number(x.f) })));
      onSaved(`${person.manager_name}: 고객사 수 저장 ${num(r.saved)}일` +
        `${r.cleared ? ` · 지움 ${num(r.cleared)}일` : ""}${r.unchanged ? ` · 기존과 같아 건너뜀 ${num(r.unchanged)}일` : ""}`);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const pending = rows.filter((r) => !r.future && r.c.stops > 0 && r.c.accounts == null).length;
  return (
    <Modal open size="lg" onClose={() => leave(onClose)}
      title={<>{person.manager_name} · {Number(month.slice(5))}월 고객사 수</>}
      footer={<>
        <span className="muted small grow">배송일 {num(rows.filter((r) => r.c.stops > 0).length)}일 · 입력 필요 {num(pending)}일 · 변경 {num(dirty.length)}일</span>
        <Button onClick={() => leave(onClose)}>닫기</Button>
        {isAdmin && (
          <Button variant="primary" onClick={save} disabled={closed || busy || dirty.length === 0 || bad.length > 0}>
            {busy ? "저장 중…" : `${num(dirty.length)}일 저장`}
          </Button>
        )}
      </>}
    >
      {error && <ErrorBox message={error} />}
      {closed && <Chip tone="warn">마감된 달 · 수정 불가 (근무 기록 › 월 표 › 마감 관리에서 해제)</Chip>}
      {bad.length > 0 && <div className="wl-block">고객사 수는 0~{MAX} 숫자로 입력하세요: {bad.map((r) => `${r.d}일`).join(", ")}</div>}
      <div className="bo-tools">
        {isAdmin && !closed && (
          <Button size="sm" variant="ghost" onClick={fill} disabled={empty.length === 0}>
            빈 칸에 주문 고객사 수 채우기 ({num(empty.length)})
          </Button>
        )}
        <span className="muted small">
          고객사 수(수거 포함)를 입력하고 Enter로 다음 날로 넘어갑니다. 금액은 저장 후 다시 계산됩니다.
          배송지 제외·조정·미지급·특수 수당·담당 변경은 [일자별]에서 처리합니다.
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
            {rows.map((r, i) => (
              <tr key={r.d} className={r.c.stops === 0 || r.future ? "off" : undefined}>
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
                <td className="num">{r.c.payable == null ? "-" : num(r.c.payable)}</td>
                <td className="num">{r.c.extras ? num(r.c.extras) : "-"}</td>
                <td className="num"><b>{num(r.c.total)}</b></td>
                <td>
                  {r.future ? <Chip tone="neutral">예정</Chip> : <Chip tone={STATUS[r.c.status][1]}>{STATUS[r.c.status][0]}</Chip>}
                  {r.dirty && <Chip tone="neutral">저장 전</Chip>}
                  {r.c.warns.length > 0 && <span className="inc-warn" title={r.c.warns.join("\n")}>⚠{r.c.warns.length}</span>}
                </td>
                <td><Button size="sm" onClick={() => leave(() => onPick(iso(r.d)))}>일자별</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}
