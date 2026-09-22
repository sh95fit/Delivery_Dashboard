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

export interface MeResp {
  email: string;
  is_admin?: boolean;
}
