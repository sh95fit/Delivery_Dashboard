import { del, http, post } from "./client";
import type { FuelType } from "./masters";

export interface FuelLog {
  id: number; vehicle_id: number; plate_no: string | null; fuel_date: string; fuel_type: FuelType;
  quantity: number | null; unit_price: number | null;
  total_amount: number; supply_amount: number; vat_amount: number; cost: number;
  station: string | null; memo: string | null; source: "manual" | "excel"; created_by: string | null;
}
export interface FuelClosing {
  total_amount: number; cost_amount: number; log_count: number;
  memo: string | null; closed_by: string | null; closed_at: string | null;
}
export interface FuelAgg { count: number; quantity: number; total: number; supply: number; vat: number; cost: number }
export interface FuelSummary {
  month: string; open_days: number; closed: FuelClosing | null; totals: FuelAgg;
  vehicles: Array<FuelAgg & { vehicle_id: number; plate_no: string | null; fuel_type: FuelType; vat_deductible: boolean }>;
  days: Array<FuelAgg & { date: string }>;
  managers: Array<{ manager_id: number | null; cost: number; vehicle_ids: number[] }>;
}
export interface FuelLogInput {
  vehicle_id: number; fuel_date: string; total_amount: number;
  supply_amount: number | null; vat_amount: number | null;
  quantity: number | null; unit_price: number | null;
  station: string | null; memo: string | null;
}

type Ok = { ok: boolean; id?: number };

export const listFuelLogs = (month: string, vehicleId?: number) =>
  http<{ month: string; closed: FuelClosing | null; items: FuelLog[] }>(
    `/api/fuel/logs?month=${month}${vehicleId ? `&vehicle_id=${vehicleId}` : ""}`);
export const addFuelLog = (body: FuelLogInput) => post<Ok>("/api/fuel/logs", body);
export const deleteFuelLog = (id: number) => del<Ok>(`/api/fuel/logs/${id}`);
export const getFuelSummary = (month: string) => http<FuelSummary>(`/api/fuel/summary?month=${month}`);
export const closeFuelMonth = (month: string, memo: string | null) =>
  post<Ok>(`/api/fuel/closings/${month}`, { memo });
export const releaseFuelMonth = (month: string, reason: string) =>
  post<Ok>(`/api/fuel/closings/${month}/release`, { reason });
