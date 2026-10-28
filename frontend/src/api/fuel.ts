import { del, download, http, post } from "./client";
import type { FuelType } from "./masters";

export interface FuelLog {
  id: number; vehicle_id: number; plate_no: string | null; fuel_date: string; fuel_type: FuelType;
  quantity: number | null; unit_price: number | null;
  total_amount: number; supply_amount: number; vat_amount: number; cost: number;
  station: string | null; memo: string | null; source: "manual" | "excel"; created_by: string | null;
  ref_price: number | null; ref_date: string | null; ref_source: "opinet" | "manual" | null; ref_diff: number | null;
}
export interface FuelClosing {
  total_amount: number; cost_amount: number; log_count: number;
  memo: string | null; closed_by: string | null; closed_at: string | null;
}
export interface FuelAgg { count: number; quantity: number; total: number; supply: number; vat: number; cost: number }
export interface FuelSummary {
  month: string; open_days: number; closed: FuelClosing | null; totals: FuelAgg;
  vehicles: Array<FuelAgg & {
    vehicle_id: number; plate_no: string | null; fuel_type: FuelType; vat_deductible: boolean;
    avg_unit: number | null; avg_ref: number | null; ref_diff: number | null;
    route_km: number; est_km: number | null; over_km: number | null; over_pct: number | null; fuel_efficiency: number | null;   // S3-P2e-2 초과 주행    
  }>;
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


/* ---------- S3-P1b-2b-3 엑셀 업로드 · 되돌리기 · 내보내기 ---------- */
export type ImportLevel = "ok" | "warn" | "need_vehicle" | "error" | "cancel";
export interface FuelImportRow {
  row: number; code: string; date: string | null; date_raw: string; product: string | null;
  fuel_type: FuelType | null; quantity: number | null; unit_price: number | null;
  total_amount: number | null; supply_amount: number | null; vat_amount: number | null; cost: number | null;
  vehicle_id: number | null; plate_no: string | null; auto: boolean; candidates: number[];
  level: ImportLevel; selectable: boolean; checked: boolean; messages: string[]; pair: number | null;
}
export interface FuelImportCode {
  code: string; rows: number; total: number; vehicle_id: number | null; auto: boolean; candidates: number[];
}
export interface FuelImportVehicle {
  id: number; plate_no: string; model: string | null; fuel_type: FuelType; vat_deductible: boolean; active: boolean;
}
export interface FuelImportPreview {
  file_name: string | null; file_kind: "xlsx" | "xls" | "html"; header_row: number; skipped: number;
  checks: Array<{ level: "ok" | "warn"; text: string }>; counts: Partial<Record<ImportLevel, number>>;
  selected: { count: number; total: number; cost: number };
  codes: FuelImportCode[]; vehicles: FuelImportVehicle[]; rows: FuelImportRow[];
}
export interface FuelImportRecord {
  id: number; file_name: string | null; date_from: string; date_to: string; log_count: number; total_amount: number;
  created_by: string | null; created_at: string | null;
  undone_by: string | null; undone_at: string | null; undo_reason: string | null; active_count: number;
}
type ImportBody = { file_name: string; content_b64: string; vehicle_map: Record<string, number> };

export const previewFuelImport = (body: ImportBody) => post<FuelImportPreview>("/api/fuel/import/preview", body);
export const commitFuelImport = (body: ImportBody & { rows: number[] }) =>
  post<{ ok: boolean; import_id: number; created: number; total: number }>("/api/fuel/import", body);
export const listFuelImports = (month: string) => http<FuelImportRecord[]>(`/api/fuel/imports?month=${month}`);
export const undoFuelImport = (id: number, reason: string) =>
  post<{ ok: boolean; deleted: number }>(`/api/fuel/imports/${id}/undo`, { reason });
export const exportFuelMonth = (month: string) =>
  download(`/api/fuel/export?month=${month}`, `유류비_${month}.xlsx`);


/* ---------- S3-P2c 일자별 단가 (오피넷 확정 · 당일 게시 · 직접 입력) ---------- */
export interface DailyPriceCell { price: number; source: "opinet" | "manual"; confirmed: boolean }
export interface DailyPrices {
  month: string; area: string | null; units: Record<FuelType, string>; notes: string[];
  days: Array<{ date: string } & Record<FuelType, DailyPriceCell | null>>;
}
export const getDailyPrices = (month: string) => http<DailyPrices>(`/api/fuel/prices/daily?month=${month}`);


/* ---------- S3-P2g-1 전기차 충전 단가 (로밍 요금 매트릭스) ---------- */
export type EvSpeed = "slow" | "mid" | "fast50" | "fast100" | "ultra";
export const EV_SPEED_LABEL: Record<EvSpeed, string> = {
  slow: "완속", mid: "중속", fast50: "급속 50~99kW", fast100: "급속 100~199kW", ultra: "초급속",
};
export interface EvSettings { ev_speed: EvSpeed; ev_km_per_kwh: number }
export interface EvRateSet {
  id: number; speed: EvSpeed; effective_from: string; issuer: string; base_price: number; rate_count: number;
  file_name: string | null; memo: string | null; created_by: string | null; created_at: string | null;
}
export interface EvRate { operator: string; price: number }
export interface EvRatePreview {
  file_name: string | null; issuer: string; base_operator: string; base_price: number; header_row: number;
  rate_count: number; skipped: number; speed: EvSpeed | null; effective_from: string | null;
  duplicate_id: number | null; rates: EvRate[];
}
export const listEvRates = () => http<{ settings: EvSettings; sets: EvRateSet[] }>("/api/fuel/ev-rates");
export const getEvRates = (id: number) => http<EvRate[]>(`/api/fuel/ev-rates/${id}/rates`);
export const previewEvRates = (body: { file_name: string; content_b64: string }) =>
  post<EvRatePreview>("/api/fuel/ev-rates/preview", body);
export const commitEvRates = (body: {
  file_name: string; content_b64: string; speed: EvSpeed; effective_from: string; memo: string | null;
}) => post<{ ok: boolean; id: number; rate_count: number; base_price: number }>("/api/fuel/ev-rates", body);
export const deleteEvRates = (id: number) => del<{ ok: boolean }>(`/api/fuel/ev-rates/${id}`);
export const saveEvSettings = (body: EvSettings) => post<EvSettings>("/api/fuel/ev-rates/settings", body);

/* S3-P2g-1d 여러 파일 한 번에 (최대 5개) — 읽지 못한 파일은 error에 이유, 나머지 칸은 비어 있음 */
export type EvRateBatchPreview = EvRatePreview & { error: string | null };
export const previewEvRatesBatch = (files: Array<{ file_name: string; content_b64: string }>) =>
  post<EvRateBatchPreview[]>("/api/fuel/ev-rates/batch/preview", { files });
export const commitEvRatesBatch = (items: Array<{
  file_name: string; content_b64: string; speed: EvSpeed; effective_from: string; memo: string | null;
}>) => post<{ ok: boolean; saved: Array<{ id: number; speed: EvSpeed; rate_count: number; base_price: number }> }>(
  "/api/fuel/ev-rates/batch", { items });
