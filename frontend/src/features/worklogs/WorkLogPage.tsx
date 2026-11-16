import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import PageLayout from "@/layouts/PageLayout";
import { useMe } from "@/layouts/shell";
import { listManagers } from "@/api/masters";
import type { ManagerRow } from "@/api/masters";
import { todayKst } from "@/lib/format";
import WorkDayTab from "./WorkDayTab";
import WorkMonthTab from "./WorkMonthTab";

type Tab = "day" | "month";

export default function WorkLogPage() {
  const isAdmin = Boolean(useMe()?.is_admin);
  const [sp] = useSearchParams();      // [S3-P2j] 물류비 확인 사항 바로가기 (?tab=month&month= / ?tab=day&date=)
  const qd = sp.get("date") ?? "";
  const qm = sp.get("month") ?? "";
  const qDate = /^\d{4}-\d{2}-\d{2}$/.test(qd) ? qd : null;
  const qMonth = /^\d{4}-\d{2}$/.test(qm) ? qm : null;
  const [tab, setTab] = useState<Tab>(sp.get("tab") === "month" ? "month" : "day");
  const [date, setDate] = useState(qDate ?? todayKst());
  const [month, setMonth] = useState(qMonth ?? (qDate ?? todayKst()).slice(0, 7));
  const [managers, setManagers] = useState<ManagerRow[]>([]);
  const [ver, setVer] = useState(0);          // 월 표 팝업 저장 → 일일 입력 다시 불러오기

  useEffect(() => { listManagers().then((r) => setManagers(r.items)).catch(() => setManagers([])); }, []);

  return (
    <PageLayout title="근무 기록">
      <div className="seg wl-tabs">
        <button type="button" className={tab === "day" ? "on" : undefined} onClick={() => setTab("day")}>일일 입력</button>
        <button type="button" className={tab === "month" ? "on" : undefined} onClick={() => setTab("month")}>월 표</button>
      </div>
      {/* 일일 입력은 숨기기만 해서 탭을 오가도 입력 중인 값 유지 */}
      <div hidden={tab !== "day"}>
        <WorkDayTab date={date} managers={managers} isAdmin={isAdmin} reloadKey={ver}
          onDate={(d) => { setDate(d); setMonth(d.slice(0, 7)); }} />
      </div>
      {tab === "month" && (
        <WorkMonthTab month={month} onMonth={setMonth} managers={managers} isAdmin={isAdmin}
          onSaved={() => setVer((v) => v + 1)} />
      )}
    </PageLayout>
  );
}
