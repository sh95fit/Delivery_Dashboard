import { http, post } from "./client";

export interface RouteResp {
  polyline: string;
  distance_m: number;
  duration_s: number;
  stops_count: number;
  source: "cache" | "routes_api" | "unavailable";
  mode?: "delivery" | "orders_estimate";
  origin_name?: string;
}

export const getRoute = (date: string, managerId: number) =>
  http<RouteResp>(`/api/routes/${date}/${managerId}`);

export const refreshRoute = (date: string, managerId: number) =>
  post<RouteResp>(`/api/routes/${date}/${managerId}/refresh`, {});
