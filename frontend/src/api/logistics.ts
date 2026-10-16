import { download, http } from "./client";

/* S3-P2a 물류비 (계정 × 일자) — 백엔드 logistics_service.cost_view 결과 */
export type CostKey = "labor" | "labor_est" | "ot_expected" | "incentive" | "extras" | "vehicle" | "fuel" | "fuel_est";
export type CostRow = Record<CostKey, number> & {
    net_revenue: number; cost_total: number; profit: number; cost_ratio: number | null;
    ncp_fuel: number; calc_fuel: number; route_m: number; route_km: number;   // S3-P2b 참고 (합계 제외)
};
export type CostAccount = CostRow & { manager_id: number | null; manager_name: string };
export type CostDay = CostRow & { date: string };
export interface CostView {
  from: string; to: string; days: number; today: string; open_days: number;
  timing: Record<string, number>;
  accounts: CostAccount[]; by_day: CostDay[]; totals: CostRow;
  issues: Array<{ level: "warn" | "info"; msg: string }>;
}

/** 표 칸 순서 = 엑셀 순서 */
export const COST_COLS: Array<[CostKey, string]> = [
  ["labor", "인건비"], ["labor_est", "인건비 예상"], ["ot_expected", "연장 예상"],
  ["incentive", "인센티브"], ["extras", "특수 수당"], ["vehicle", "차량비"],
  ["fuel", "유류비"], ["fuel_est", "유류비 예상"],
];

export const getCostView = (from: string, to: string) =>
  http<CostView>(`/api/logistics/cost?from=${from}&to=${to}`);
export const exportCostView = (from: string, to: string) =>
  download(`/api/logistics/export?from=${from}&to=${to}`, `물류비_${from}_${to}.xlsx`);
