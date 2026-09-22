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

export interface DeliveryResp {
  date: string;
  summary: { stops: number; meals: number; accounts: number };
  managers: {
    manager_id: number;
    stops: number;
    meals: number;
    accounts: number;
  }[];
  // 필요 시 필드 확장
}

export interface RevenueResp {
  from: string;
  to: string;
  total_net_revenue: number;
  // 필요 시 필드 확장
}

async function http<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin" });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  status: (date: string) => http<StatusResp>(`/api/status/${date}`),
  deliveries: (date: string) => http<DeliveryResp>(`/api/deliveries/${date}`),
  revenue: (from: string, to: string) =>
    http<RevenueResp>(`/api/revenue/summary?from=${from}&to=${to}`),
  me: () => http<{ email: string }>("/api/me"),
};
