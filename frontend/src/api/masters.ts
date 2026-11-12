import { del, http, post, put } from "./client";

export type PayType = "monthly" | "hourly" | "none";
export type FuelType = "gasoline" | "diesel" | "lpg" | "ev";

export const PAY_LABEL: Record<PayType, string> = { monthly: "월급", hourly: "시급", none: "인건비 없음" };
export const FUEL_LABEL: Record<FuelType, string> = { gasoline: "휘발유", diesel: "경유", lpg: "LPG", ev: "전기" };
export const PERIOD_CATS: Record<string, string> = {
  insurance: "보험", tax: "자동차세", inspection: "검사", lease: "리스·렌트", other: "기타",
};
export const EXPENSE_CATS: Record<string, string> = {
  repair: "수리", maintenance: "정비·소모품", tire: "타이어", towing: "견인", accident: "사고 처리(자기부담금 등)",
  depreciation: "감가", parking: "주차", wash: "세차", other: "기타",
};

export type OpsStatus = "active" | "inactive" | "deleted" | "unknown";
export const OPS_LABEL: Record<OpsStatus, string> = {
  active: "활성", inactive: "비활성", deleted: "삭제", unknown: "확인 필요",
};

export interface ManagerRow {
  manager_id: number; name: string | null; color: string | null;
  ops_status: OpsStatus; ops_status_raw: string | null;
  active: boolean; memo: string | null;
  updated_at: string | null; updated_by: string | null;
  workers: string[];   // [S3-P2h-3a] 오늘 기준 이 계정을 고정 계정으로 가진 인력
}

export interface Vehicle {
  id: number; plate_no: string; model: string | null; fuel_type: FuelType;
  holders: Array<{ worker_id: number; name: string; since: string }>;          // [S3-P2h-3b-1] 고정 사용 인력
  day_users: Array<{ worker_id: number; name: string; reason_label: string }>; // 오늘 하루 대체 사용  
  fuel_efficiency: number | null; purchase_date: string | null; purchase_price: number | null;
  memo: string | null; active: boolean; manager_ids: number[]; vat_deductible: boolean;
  disposed_on: string | null;   // [S3-P2h-3b-2] 처분일 (판매·폐차, 없으면 null)  
}
export type VehicleInput = Omit<Vehicle, "id" | "manager_ids" | "holders" | "day_users">;   // [S3-P2h-3b-1] 표시용 칸은 저장 값에서 제외

export interface PeriodCost {
  id: number; vehicle_id: number; plate_no: string | null; category: string; amount: number;
  start_date: string; end_date: string; days: number; daily: number;
  memo?: string | null; created_by?: string | null;
}
export interface Expense {
  id: number; vehicle_id: number; plate_no: string | null; expense_date: string; category: string;
  amount: number; memo?: string | null; created_by?: string | null;
}
export interface CostSummary {
  from: string; to: string; days: number;
  vehicles: Array<{ vehicle_id: number; plate_no: string | null; period_cost: number; expense: number; fuel: number;
    expense_by_category: Record<string, number> }>;
  totals: { period_cost: number; expense: number; fuel: number };
  fuel_estimated: string[];
}

type Ok = { ok: boolean; id?: number };

// 매니저(계정) — [S3-P2h-3a] 대시보드 상태·메모만. 급여는 인력 계약 조건, 차량은 인력 차량 이용
export const listManagers = () => http<{ items: ManagerRow[] }>("/api/managers");
export const saveManagerProfile = (id: number, body: { active: boolean; memo: string | null }) =>
  put<Ok>(`/api/managers/${id}/profile`, body);

// 차량
export const listVehicles = () => http<{ items: Vehicle[] }>("/api/vehicles");
export const createVehicle = (body: VehicleInput) => post<Ok>("/api/vehicles", body);
export const updateVehicle = (id: number, body: VehicleInput) => put<Ok>(`/api/vehicles/${id}`, body);
export const deleteVehicle = (id: number) => del<Ok>(`/api/vehicles/${id}`);

// 기간 비용
export const listPeriodCosts = (vehicleId?: number) =>
  http<{ items: PeriodCost[] }>(`/api/vehicles/period-costs${vehicleId ? `?vehicle_id=${vehicleId}` : ""}`);
export const addPeriodCost = (body: { vehicle_id: number; category: string; amount: number;
  start_date: string; end_date: string; memo: string | null }) => post<Ok>("/api/vehicles/period-costs", body);
export const deletePeriodCost = (id: number) => del<Ok>(`/api/vehicles/period-costs/${id}`);

// 지출 내역
export const listExpenses = (from: string, to: string, vehicleId?: number) =>
  http<{ items: Expense[] }>(`/api/vehicles/expenses?from=${from}&to=${to}${vehicleId ? `&vehicle_id=${vehicleId}` : ""}`);
export const addExpense = (body: { vehicle_id: number; expense_date: string; category: string;
  amount: number; memo: string | null }) => post<Ok>("/api/vehicles/expenses", body);
export const deleteExpense = (id: number) => del<Ok>(`/api/vehicles/expenses/${id}`);

export const getCostSummary = (from: string, to: string) =>
  http<CostSummary>(`/api/vehicles/cost-summary?from=${from}&to=${to}`);

// [S3-P2h-3d-2b] 월별 계정 → 인력 → 차량 정합성 표 (읽기 전용)
export type BoardFlag = "no_worker" | "after_end" | "no_vehicle" | "disposed" | "shared";
export interface BoardCell {
  worker_id: number | null; worker_name: string | null; vehicle_id: number | null; plate_no: string | null;
  src: "chosen" | "log" | "fixed" | null; basis: string | null; flags: BoardFlag[];
  ex: string | null;   // [S3-P2h-3d-5] 점검 제외 사유 (고칠 칸인데 제외된 경우만)
}
export interface BoardRow {
  manager_id: number; name: string; color: string | null; cells: Record<string, BoardCell>;
  run_days: number; counts: Record<BoardFlag, number>; ex_days: number;
}
export interface BoardSpan { worker_id: number; name: string | null; start: string | null; end: string | null }
export interface AssignBoard {
  month: string; last_day: number; flags: Record<BoardFlag, string>; errors: BoardFlag[];
  rows: BoardRow[]; totals: Record<BoardFlag, number>;
  overlaps: Array<{ kind: "account" | "vehicle"; value: number; label: string; from: string | null; first: BoardSpan; second: BoardSpan }>;
  unused_vehicles: string[];
  excluded: number; exclude_reasons: Record<ExcludeReason, string>; excludes: BoardExclude[];   // [S3-P2h-3d-5]
}
export const getAssignBoard = (month: string) => http<AssignBoard>(`/api/vehicles/assign-board?month=${month}`);

// [S3-P2h-3d-5] 배정 점검 제외 계정 (표시만 — 인센티브·물류비 계산은 그대로)
export type ExcludeReason = "internal" | "hold" | "other";
export interface BoardExclude {
  id: number; manager_id: number; name: string; reason: ExcludeReason; reason_label: string;
  start_date: string; end_date: string | null; memo: string | null; created_by: string | null;
}
export const addBoardExclude = (body: { manager_id: number; reason: ExcludeReason; start_date: string;
  end_date: string | null; memo: string | null }) => post<Ok>("/api/vehicles/assign-board/excludes", body);
export const deleteBoardExclude = (id: number) => del<Ok>(`/api/vehicles/assign-board/excludes/${id}`);
