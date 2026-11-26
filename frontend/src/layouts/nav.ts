import type { IconName } from "./Icon";

/** label은 한글 7자 이내. 긴 정식 명칭은 hint(마우스 오버 표시)로.
 *  page = 백엔드 PAGE_KEYS 화면키(R 권한이 있어야 메뉴 표시). superOnly = 시스템 마스터 전용. */
export type NavItem = {
  to: string; label: string; hint?: string; icon: IconName; ready: boolean; step?: string;
  page?: string; superOnly?: boolean;
};
export type NavSection = { section: string; items: NavItem[] };

export const NAV: NavSection[] = [
  {
    section: "운영",
    items: [
      { to: "/", label: "대시보드", icon: "dashboard", ready: true, page: "dashboard" },
      { to: "/ops/packing", label: "포장 그룹", icon: "box", ready: false, step: "P2", page: "packing" },
      { to: "/ops/work", label: "근무 기록", hint: "지문 시각 입력 · 월 근무표", icon: "clock", ready: true, page: "worklogs" },
    ],
  },
  {
    section: "재무",
    items: [
      { to: "/finance/revenue", label: "매출 관리", icon: "won", ready: false, step: "P7", page: "sales" },
      { to: "/finance/cost", label: "물류비", hint: "매출 대비 인건비·인센티브·차량비·유류비", icon: "wallet", ready: true, page: "logistics" },
      { to: "/finance/incentive", label: "인센티브·수당", hint: "고객사 수 입력 · 배송지 제외 · 미지급 · 특수 수당", icon: "gift", ready: true, page: "incentive" },
      { to: "/finance/grid", label: "매출·비용 분석", icon: "grid", ready: false, step: "P8", page: "analysis" },
    ],
  },
  {
    section: "도구",
    items: [
      { to: "/tools/simulation", label: "시뮬레이션", hint: "신규 고객사 시뮬레이션", icon: "route", ready: false, step: "P9", page: "simulation" },
    ],
  },
  {
    section: "설정",
    items: [
      { to: "/settings/workers", label: "인력", hint: "사람별 계약·지정 근무·고정 계정", icon: "users", ready: true, page: "workers" },
      { to: "/settings/managers", label: "매니저 계정", hint: "운영 앱 배송 계정 (이름·색·운영 상태)", icon: "idcard", ready: true, page: "managers" },
      { to: "/settings/vehicles", label: "차량·지출", hint: "차량 · 유류비", icon: "truck", ready: true, page: "vehicles" },
      { to: "/settings/internal", label: "직원식", hint: "직원식 대상 설정", icon: "tag", ready: true, page: "internal" },
      { to: "/settings/permissions", label: "권한", hint: "사용자 · 권한셋 (마스터 전용)", icon: "lock", ready: true, superOnly: true },
    ],
  },
];
