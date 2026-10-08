import { useEffect, useState } from "react";
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
  const [tab, setTab] = useState<Tab>("day");
  const [date, setDate] = useState(todayKst());
  const [month, setMonth] = useState(todayKst().slice(0, 7));
  const [managers, setManagers] = useState<ManagerRow[]>([]);

  useEffect(() => { listManagers().then((r) => setManagers(r.items)).catch(() => setManagers([])); }, []);

  return (
    <PageLayout title="근무 기록">
      <div className="seg wl-tabs">
        <button type="button" className={tab === "day" ? "on" : undefined} onClick={() => setTab("day")}>일일 입력</button>
        <button type="button" className={tab === "month" ? "on" : undefined} onClick={() => setTab("month")}>월 표</button>
      </div>
      {/* 일일 입력은 숨기기만 해서 탭을 오가도 입력 중인 값 유지 */}
      <div hidden={tab !== "day"}>
        <WorkDayTab date={date} managers={managers} isAdmin={isAdmin}
          onDate={(d) => { setDate(d); setMonth(d.slice(0, 7)); }} />
      </div>
      {tab === "month" && (
        <WorkMonthTab month={month} onMonth={setMonth}
          onPickDay={(d) => { setDate(d); setTab("day"); }} />
      )}
    </PageLayout>
  );
}
