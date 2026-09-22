import { http, post } from "./client";

export interface RouteSummary {
  manager_id: number;
  manager_name?: string | null;
  manager_color?: string | null;
  mode: "preview" | "live" | "result";
  completed_polyline: string;
  remaining_polyline: string;
  distance_m: number;
  duration_s: number;
  completed_stops: number;
  remaining_stops: number;
  origin_name?: string | null;
  source: "cache" | "routes_api" | "unavailable";
}

export interface AllRoutesResp {
  date: string;
  state: "PREVIEW" | "LIVE" | "RESULT" | "NONE";
  source: "delivery" | "orders_estimate";
  routes: RouteSummary[];
}

export const getAllRoutes = (date: string) =>
  http<AllRoutesResp>(`/api/routes/${date}`);

export const getRoute = (date: string, managerId: number) =>
  http<RouteSummary>(`/api/routes/${date}/${managerId}`);

export const refreshRoute = (date: string, managerId: number) =>
  post<RouteSummary>(`/api/routes/${date}/${managerId}/refresh`, {});
