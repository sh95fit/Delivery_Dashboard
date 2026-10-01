export type StatusState = "PREVIEW" | "LIVE" | "RESULT" | "NONE";

export interface DayTotals {
  stops: number;
  accounts: number;
  meals: number;
  lunch_meals: number;
  dinner_meals: number;
  web_qty: number;
  admin_qty: number;
  app_qty: number;
  app_converted_qty: number;
  app_pending_qty: number;
  refund_qty: number;
  gross_revenue: number;
  refund_amount: number;
  net_revenue: number;
  estimated_revenue: number;
  completed_stops: number;
  unassigned_stops: number;
  no_coord_stops: number;
  internal_stops: number;
  internal_meals: number;
  internal_gross: number;
  internal_refund: number;
  internal_net: number;
}

export interface DayWarnings {
  cancelled_orders?: number;
  cancelled_qty?: number;
  cancelled_stops?: number;
  cancelled_by_source?: Record<string, { orders: number; qty: number }>;
  unconverted_app_qty?: number;
  insufficient_records?: number | null;
  app_unmatched_address_qty?: number;
  app_unmapped_product_qty?: number;
  app_blocked_qty?: number;
  unplaced_lines?: number;
  unplaced_qty?: number;
  no_coord_stops?: number;
}

export interface InternalPlace {
  address_id: number | null;
  address_name?: string | null;
  manager_name?: string | null;
  meals: number;
  net_revenue: number;
  delivered: boolean;
}

export interface InternalView {
  enabled: boolean;
  stops: number;
  meals: number;
  gross_revenue: number;
  refund_amount: number;
  net_revenue: number;
  by_lineup: Record<string, { name: string; meal: string; qty: number; net_revenue: number }>;
  places: InternalPlace[];
}

export interface StatusResp {
  date: string;
  state: StatusState;
  incomplete: number;
  cutoff_at: string;
  now: string;
  progress: { completed: number; total: number; unassigned: number };
  estimate: null | {
    total: number;
    estimated_meals: number;
    estimated_accounts: number;
    estimated_net_revenue: number;
  };
  source?: string | null;
  mode?: string | null;
  cutoff_source?: string | null;
  estimated?: boolean;
  totals?: DayTotals | null;
  warnings?: DayWarnings | null;
  internal?: InternalView | null;
}

export interface StopLineup {
  name: string;
  qty: number;
  amount?: number | null;
  internal_qty?: number;
}

export interface LineupSummary {
  name: string;
  meal: "lunch" | "dinner" | string;
  qty: number;
  refund_qty: number;
  gross_revenue: number;
  refund_amount: number;
  net_revenue: number;
  internal_qty: number;
  internal_net: number;
}

export interface ManagerRow {
  manager_id: number | null;
  manager_name?: string | null;
  color?: string | null;
  stops: number;
  meals: number;
  accounts: number;
  net_revenue: number;
  gross_revenue: number;
  refund_amount: number;
  lunch_meals: number;
  dinner_meals: number;
  web_qty: number;
  admin_qty: number;
  app_qty: number;
  app_pending_qty: number;
  internal_stops: number;
  internal_meals: number;
  internal_net: number;
  lineups?: Record<string, StopLineup>;
}

export interface StopPoint {
  delivery_id: string;
  address_id: number | null;
  address_name?: string | null;
  detail_address?: string | null;
  latitude: number | null;
  longitude: number | null;
  has_coord?: boolean;
  delivery_hour_raw?: string | null;
  delivery_time?: string | null;
  manager_id?: number | null;
  manager_name?: string | null;
  manager_color?: string | null;
  delivered_at?: string | null;
  accounts: number;
  meals: number;
  lunch_meals: number;
  dinner_meals: number;
  app_qty: number;
  app_pending_qty: number;
  net_revenue: number;
  is_internal: boolean;
  internal_meals: number;
  internal_net: number;
  lineups: Record<string, StopLineup>;
}

export interface DeliveryResp {
  date: string;
  source: string;
  mode?: string | null;
  estimated?: boolean;
  cutoff_at?: string | null;
  summary: DayTotals & { total_qty?: number; unconfirmed_stops?: number; unconfirmed_qty?: number };
  managers: ManagerRow[];
  unassigned?: { stops: number };
  stops: StopPoint[];
  by_lineup?: Record<string, LineupSummary>;
  warnings?: DayWarnings;
  internal?: InternalView;
}

export interface RouteSummary {
  manager_id: number;
  manager_name?: string | null;
  manager_color?: string | null;
  mode: "preview" | "live" | "result";
  completed_path: Array<{ lat: number; lng: number }>;
  remaining_path: Array<{ lat: number; lng: number }>;
  distance_m: number;
  duration_ms: number;
  completed_stops: number;
  remaining_stops: number;
  toll_fare: number;
  fuel_price_naver: number;
  fuel_price_opinet?: number | null;
  origin_name?: string | null;
  origin_latitude?: number | null;
  origin_longitude?: number | null;
  source: "cache" | "naver" | "pending" | "unavailable";
  completed_stop_ids?: Array<string | number>;
  remaining_stop_ids?: Array<string | number>;
  payload?: Record<string, unknown>;
  status?: string;
}

export interface AllRoutesResp {
  date: string;
  state: "PREVIEW" | "LIVE" | "RESULT" | "NONE";
  source: "delivery" | "orders_estimate";
  routes: RouteSummary[];
}

export interface MeResp {
  email: string;
  is_admin?: boolean;
}
