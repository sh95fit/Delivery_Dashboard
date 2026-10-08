import type { IconName } from "./Icon";

/** label은 한글 7자 이내. 긴 정식 명칭은 hint(마우스 오버 표시)로. */
export type NavItem = { to: string; label: string; hint?: string; icon: IconName; ready: boolean; step?: string };
export type NavSection = { section: string; items: NavItem[] };

export const NAV: NavSection[] = [
  {
    section: "운영",
    items: [
      { to: "/", label: "대시보드", icon: "dashboard", ready: true },
      { to: "/ops/packing", label: "포장 그룹", icon: "box", ready: false, step: "P2" },
      { to: "/ops/work", label: "근무 기록", hint: "지문 시각 입력 · 월 근무표", icon: "clock", ready: true },
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
    items: [
      { to: "/tools/simulation", label: "시뮬레이션", hint: "신규 고객사 시뮬레이션", icon: "route", ready: false, step: "P9" },
    ],
  },
  {
    section: "설정",
    items: [
      { to: "/settings/workers", label: "인력", hint: "사람별 계약·지정 근무·고정 계정", icon: "users", ready: true },
      { to: "/settings/managers", label: "매니저 계정", hint: "운영 앱 배송 계정 (이름·색·운영 상태)", icon: "idcard", ready: true },
      { to: "/settings/vehicles", label: "차량·지출", icon: "truck", ready: true },
      { to: "/settings/internal", label: "직원식", hint: "직원식 대상 설정", icon: "tag", ready: true },
      { to: "/settings/permissions", label: "권한", icon: "lock", ready: false, step: "P11" },
    ],
  },
];
