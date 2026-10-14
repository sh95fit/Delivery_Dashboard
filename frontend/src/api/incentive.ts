import { del, http, post, put } from "./client";

export type IncStatus = "ok" | "held" | "need_accounts" | "no_rate";
export type ExcludeReason = "quick" | "other_manager" | "not_delivered" | "other";
export type BandKind = "product" | "account";
export interface Band { start: number; end: number | null; amount: number }
export interface RateSet {
  id: number; effective_from: string; memo: string | null; created_by: string | null;
  bands: Record<BandKind, Band[]>; current?: boolean;
}
export interface Exclusion {
  id: number; address_id: number; reason: ExcludeReason; reason_label: string; memo: string | null;
  created_by: string | null; created_at: string | null;
}
export interface ExtraRow {
  id: number; item_id: number; item_name: string; qty: number; unit_amount: number; amount: number;
  memo: string | null; created_by: string | null; created_at: string | null;
}
export interface QtyAdj {
  id: number; product_id: number | null; label: string; qty: number; reason: string;
  created_by: string | null; created_at: string | null;
}
export interface IncLineup { product_id: number; label: string; auto: number; excluded: number; adjust: number; final: number }
export interface HoldRow { id: number; reason: string; created_by: string | null; created_at: string | null }
export interface AdjInfo { value: number; reason: string | null; created_by: string | null; created_at: string | null }
export interface IncStop {
  address_id: number; address_name: string | null; gajung_qty: number; fresh_qty: number; light_qty: number;
  mil_qty: number; dinner_qty: number; pilot_qty: number; order_accounts: number; shared: boolean;
  exclusion: Exclusion | null;
}
export interface IncDayRow {
  manager_id: number; manager_name: string; color: string | null;
  stops: number; gajung_qty: number; fresh_qty: number; light_qty: number; mil_qty: number;
  dinner_qty: number; pilot_qty: number;
  auto_qty: number; excluded_qty: number; adj_total: number; delta: number; lineups: IncLineup[];
  product_total: number; accounts: number | null;
  product_incentive: number | null; product_unit: number | null;
  account_incentive: number | null; account_unit: number | null;
  incentive: number | null; held: boolean; payable: number | null; extras: number; total: number;
  status: IncStatus; warns: string[]; order_accounts: number;
  stop_list: IncStop[]; exclusions: Exclusion[]; adj_list: QtyAdj[]; extra_list: ExtraRow[]; hold_list: HoldRow[];
  accounts_info: AdjInfo | null;
  owner: IncOwner;
}
export interface ExtraItem {
  id: number; name: string; unit_amount: number | null; active: boolean; sort_order: number; memo: string | null;
}
export interface IncDayView {
  date: string; closed: boolean; future: boolean; rate: RateSet | null; extra_items: ExtraItem[];
  exclude_reasons: Record<ExcludeReason, string>;
  adj_lineups: Array<{ product_id: number | null; label: string }>;
  items: IncDayRow[];
  workers: IncWorkerOpt[];
  totals: { payable: number; extras: number; total: number; need_accounts: number; held: number };
}
export interface IncMonthCell {
  payable: number | null; extras: number; total: number; status: IncStatus;
  product_total: number; accounts: number | null; stops: number; warn: boolean;
}
export interface IncMonthPerson {
  manager_id: number; manager_name: string; color: string | null; days: Record<string, IncMonthCell>;
  sum: { incentive: number; extras: number; total: number; work_days: number; held_days: number;
         pending_days: number; warn_days: number };
}
export interface IncMonthView {
  month: string; last_day: number; closed: boolean; people: IncMonthPerson[];
  totals: { incentive: number; extras: number; total: number; pending_days: number };
}
type Ok = { ok: boolean };
type Warned = Ok & { id: number; warns: string[] };

export const getIncDay = (d: string) => http<IncDayView>(`/api/incentive/day?d=${d}`);
export const getIncMonth = (ym: string) => http<IncMonthView>(`/api/incentive/month?month=${ym}-01`);
export const saveIncAccounts = (d: string, items: Array<{ manager_id: number; value: number | null }>) =>
  put<{ ok: boolean; saved: number; cleared: number; unchanged: number }>(`/api/incentive/accounts/${d}`, { items });
export const addQtyAdj = (b: { work_date: string; manager_id: number; product_id: number | null; qty: number; reason: string }) =>
  post<Ok & { id: number }>("/api/incentive/qty-adjustments", b);
export const deleteQtyAdj = (id: number, reason: string) =>
  post<Ok>(`/api/incentive/qty-adjustments/${id}/delete`, { reason });
export const addExclusion = (b: { work_date: string; manager_id: number; address_id: number;
  reason: ExcludeReason; memo: string | null }) => post<Ok & { id: number }>("/api/incentive/exclusions", b);
export const deleteExclusion = (id: number) => del<Ok>(`/api/incentive/exclusions/${id}`);
export const addExtra = (b: { work_date: string; manager_id: number; item_id: number; qty: number;
  unit_amount: number; memo: string | null }) => post<Warned>("/api/incentive/extras", b);
export const updateExtra = (id: number, b: { qty: number; unit_amount: number; memo: string | null }) =>
  put<Warned>(`/api/incentive/extras/${id}`, b);
export const deleteExtra = (id: number, reason: string) => post<Ok>(`/api/incentive/extras/${id}/delete`, { reason });
export const addHold = (d: string, manager_id: number, reason: string) =>
  post<Ok>(`/api/incentive/holds/${d}`, { manager_id, reason });
export const releaseHold = (id: number, reason: string) => post<Ok>(`/api/incentive/holds/${id}/release`, { reason });

export type RateSetInput = { effective_from: string; memo: string | null; product: Band[]; account: Band[] };
export const getRates = () => http<{ items: RateSet[] }>("/api/incentive/rates");
export const saveRates = (id: number | null, b: RateSetInput) =>
  id == null ? post<Ok>("/api/incentive/rates", b) : put<Ok>(`/api/incentive/rates/${id}`, b);
export const deleteRates = (id: number) => del<Ok>(`/api/incentive/rates/${id}`);

/** unit_amount: 숫자 = 고정 금액(기본 단가), null = 수시 입력 */
export type ExtraItemInput = { name: string; unit_amount: number | null; active: boolean; sort_order: number; memo: string | null };
export const getExtraItems = () => http<{ items: ExtraItem[] }>("/api/incentive/extra-items");
export const saveExtraItem = (id: number | null, b: ExtraItemInput) =>
  id == null ? post<Ok>("/api/incentive/extra-items", b) : put<Ok>(`/api/incentive/extra-items/${id}`, b);

export interface IncPerson {
  worker_id: number; name: string; income_type: string | null; active: boolean; pay_type: string | null;
  on_sheet: boolean; incentive: number; extras: number; total: number; days: number; pending_days: number;
  chosen_days: number;
}
export interface IncUnassigned {
  date: string; manager_id: number; manager_name: string; amount: number; pending: boolean; why: string | null;
}
export interface IncPeopleView {
  month: string; people: IncPerson[]; unassigned: IncUnassigned[];
  totals: { incentive: number; extras: number; total: number; on_sheet: number; off_sheet: number; unassigned: number };
}
export const getIncPeople = (ym: string) => http<IncPeopleView>(`/api/incentive/people?month=${ym}-01`);

export type OwnerSource = "chosen" | "log" | "fixed";
export interface IncOwner {
  worker_id: number | null; name: string | null; source: OwnerSource | null; why: string | null; memo: string | null;
}
export interface IncWorkerOpt { worker_id: number; name: string; pay_type: string | null; fixed_name: string | null }
export const saveIncOwner = (d: string, b: { manager_id: number; worker_id: number | null; memo: string | null }) =>
  put<Ok & { changed: boolean }>(`/api/incentive/owners/${d}`, b);
