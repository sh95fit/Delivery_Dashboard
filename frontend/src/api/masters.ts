import { del, http, post, put } from "./client";

export type PayType = "monthly" | "hourly" | "none";
export type FuelType = "gasoline" | "diesel" | "lpg" | "ev";

export const PAY_LABEL: Record<PayType, string> = { monthly: "월급", hourly: "시급", none: "인건비 없음" };
export const FUEL_LABEL: Record<FuelType, string> = { gasoline: "휘발유", diesel: "경유", lpg: "LPG", ev: "전기" };
export const PERIOD_CATS: Record<string, string> = { insurance: "보험", tax: "자동차세", inspection: "검사", other: "기타" };
export const EXPENSE_CATS: Record<string, string> = {
  repair: "수리", maintenance: "정비·소모품", tire: "타이어", depreciation: "감가",
  parking: "주차", wash: "세차", other: "기타",
};

export interface PayRate {
  id: number; pay_type: PayType; amount: number; effective_from: string;
  memo?: string | null; created_by?: string | null;
}
export interface Assignment {
  id: number; vehicle_id: number | null; plate_no?: string | null; model?: string | null;
  start_date: string; created_by?: string | null;
}
export interface ManagerRow {
  manager_id: number; name: string | null; color: string | null;
  recent_stops: number; last_date: string | null;
  active: boolean; memo: string | null;
  pay: PayRate | null;
  vehicle: { vehicle_id: number; plate_no: string; model?: string | null } | null;
}
export interface ManagerDetail { rates: PayRate[]; assignments: Assignment[] }

export interface Vehicle {
  id: number; plate_no: string; model: string | null; fuel_type: FuelType;
  fuel_efficiency: number | null; purchase_date: string | null; purchase_price: number | null;
  memo: string | null; active: boolean; manager_ids: number[];
}
export type VehicleInput = Omit<Vehicle, "id" | "manager_ids">;

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
  vehicles: Array<{ vehicle_id: number; plate_no: string | null; period_cost: number; expense: number;
    expense_by_category: Record<string, number> }>;
  totals: { period_cost: number; expense: number };
}

type Ok = { ok: boolean; id?: number };

// 매니저
export const listManagers = () => http<{ items: ManagerRow[] }>("/api/managers");
export const getManager = (id: number) => http<ManagerDetail>(`/api/managers/${id}`);
export const saveManagerProfile = (id: number, body: { active: boolean; memo: string | null }) =>
  put<Ok>(`/api/managers/${id}/profile`, body);
export const addPayRate = (id: number, body: { pay_type: PayType; amount: number; effective_from: string; memo: string | null }) =>
  post<Ok>(`/api/managers/${id}/rates`, body);
export const deletePayRate = (rateId: number) => del<Ok>(`/api/managers/rates/${rateId}`);
export const assignVehicle = (id: number, body: { vehicle_id: number | null; start_date: string }) =>
  post<Ok>(`/api/managers/${id}/vehicle`, body);
export const deleteAssignment = (aid: number) => del<Ok>(`/api/managers/assignments/${aid}`);

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
