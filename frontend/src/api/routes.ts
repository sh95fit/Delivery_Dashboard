import { http } from "./client";

export interface RouteResp {
  polyline: string;
  distance_m: number;
  duration_s: number;
  stops_count: number;
  source: "cache" | "routes_api" | "unavailable";
}

export const getRoute = (date: string, managerId: number) =>
  http<RouteResp>(`/api/routes/${date}/${managerId}`);