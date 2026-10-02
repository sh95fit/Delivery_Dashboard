import type { IconName } from "./Icon";

export type NavItem = { to: string; label: string; icon: IconName; ready: boolean; step?: string };
export type NavSection = { section: string; items: NavItem[] };

/** ready=false 메뉴는 '준비' 표시만 하고 이동하지 않는다. 단계 완료 시 true로 바꾸고 routes.tsx에 등록. */
export const NAV: NavSection[] = [
  {
    section: "운영",
    items: [
      { to: "/", label: "대시보드", icon: "dashboard", ready: true },
      { to: "/ops/packing", label: "포장 그룹", icon: "box", ready: false, step: "P2" },
      { to: "/ops/work", label: "근무 입력", icon: "clock", ready: false, step: "P4" },
    ],
  },
  {
    section: "재무",
    items: [
      { to: "/finance/revenue", label: "매출 관리", icon: "won", ready: false, step: "P7" },
      { to: "/finance/cost", label: "비용 관리", icon: "wallet", ready: false, step: "P7" },
      { to: "/finance/incentive", label: "인센티브·수당", icon: "gift", ready: false, step: "P7" },
      { to: "/finance/grid", label: "매출·비용 분석", icon: "grid", ready: false, step: "P8" },
    ],
  },
  {
    section: "도구",
    items: [{ to: "/tools/simulation", label: "신규 고객사 시뮬레이션", icon: "route", ready: false, step: "P9" }],
  },
  {
    section: "설정",
    items: [
      { to: "/settings/managers", label: "매니저", icon: "users", ready: false, step: "P1" },
      { to: "/settings/vehicles", label: "차량·지출", icon: "truck", ready: false, step: "P1" },
      { to: "/settings/internal", label: "직원식", icon: "tag", ready: true },
      { to: "/settings/permissions", label: "권한", icon: "lock", ready: false, step: "P11" },
    ],
  },
];
