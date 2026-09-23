export type StatusState = "PREVIEW" | "LIVE" | "RESULT" | "NONE";

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
}

export interface StopLineup {
  name: string;
  qty: number;
  amount?: number;
}

export interface ManagerRow {
  manager_id: number;
  manager_name?: string | null;
  color?: string | null;
  stops: number;
  meals: number;
  accounts: number;
  net_revenue?: number;
  lineups?: Record<string, StopLineup>;
}

export interface StopPoint {
  delivery_id: string;
  address_id: number;
  address_name?: string | null;
  detail_address?: string | null;
  latitude: number;
  longitude: number;
  delivery_hour_raw?: string | null;
  delivery_time?: string | null;
  manager_id?: number | null;
  manager_name?: string | null;
  manager_color?: string | null;
  accounts: number;
  meals: number;
  lineups: Record<string, StopLineup>;
}

export interface DeliveryResp {
  date: string;
  source: "delivery" | "orders_estimate";
  summary: {
    stops: number;
    meals: number;
    accounts: number;
    completed_stops?: number;
    unassigned_stops?: number;
  };
  managers: ManagerRow[];
  unassigned?: { stops: number };
  stops: StopPoint[];
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

