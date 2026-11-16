import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import PageLayout from "@/layouts/PageLayout";
import { useMe } from "@/layouts/shell";
import { todayKst } from "@/lib/format";
import IncentiveDayTab from "./IncentiveDayTab";
import IncentiveMonthTab from "./IncentiveMonthTab";
import IncentiveRatesTab from "./IncentiveRatesTab";
import IncentivePeopleTab from "./IncentivePeopleTab";

type Tab = "day" | "month" | "people" | "rates";

export default function IncentivePage() {
  const isAdmin = Boolean(useMe()?.is_admin);
  const [sp] = useSearchParams();      // [S3-P2j] 물류비 확인 사항 바로가기 (?tab=month&month=)
  const qt = sp.get("tab");
  const qd = sp.get("date") ?? "";
  const qm = sp.get("month") ?? "";
  const qDate = /^\d{4}-\d{2}-\d{2}$/.test(qd) ? qd : null;
  const qMonth = /^\d{4}-\d{2}$/.test(qm) ? qm : null;
  const [tab, setTab] = useState<Tab>(qt === "month" || qt === "people" || qt === "rates" ? qt : "day");
  const [date, setDate] = useState(qDate ?? todayKst());
  const [month, setMonth] = useState(qMonth ?? (qDate ?? todayKst()).slice(0, 7));
  const dirty = useRef(0);

  function pick(d: string) {
    if (d !== date && dirty.current > 0 && !confirm(`일자별 입력에 저장하지 않은 고객사 수 ${dirty.current}건이 있습니다. 취소하고 이동할까요?`)) return;
    setDate(d);
    setTab("day");
  }
  const tabBtn = (t: Tab, label: string) => (
    <button type="button" className={tab === t ? "on" : undefined} onClick={() => setTab(t)}>{label}</button>
  );

  return (
    <PageLayout title="인센티브·수당">
      <div className="seg wl-tabs">
        {tabBtn("day", "일자별 입력")}
        {tabBtn("month", "월 보드")}
        {isAdmin && tabBtn("people", "담당자별 목록")}
        {tabBtn("rates", "단가표·품목")}
      </div>
      {/* 일자별 입력은 숨기기만 해서 탭을 오가도 입력 중인 값 유지 */}
      <div hidden={tab !== "day"}>
        <IncentiveDayTab date={date} isAdmin={isAdmin} onDirty={(n) => { dirty.current = n; }}
          onDate={(d) => { setDate(d); setMonth(d.slice(0, 7)); }} />
      </div>
      {tab === "month" && <IncentiveMonthTab month={month} onMonth={setMonth} onPick={pick} isAdmin={isAdmin} />}
      {tab === "people" && isAdmin && <IncentivePeopleTab month={month} onMonth={setMonth} />}
      {tab === "rates" && <IncentiveRatesTab isAdmin={isAdmin} />}
    </PageLayout>
  );
}
