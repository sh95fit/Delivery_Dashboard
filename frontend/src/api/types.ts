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

export interface ManagerRow {
  manager_id: number;
  manager_name?: string | null;
  color?: string | null;
  stops: number;
  meals: number;
  accounts: number;
  net_revenue?: number;
}

export interface DeliveryResp {
  date: string;
  summary: {
    stops: number;
    meals: number;
    accounts: number;
    completed_stops?: number;
    unassigned_stops?: number;
  };
  managers: ManagerRow[];
  unassigned?: { stops: number };
}

export interface MeResp {
  email: string;
  is_admin?: boolean;
}
