import { http } from "./client";
import type { DeliveryResp } from "./types";

export const getDeliveries = (date: string) => http<DeliveryResp>(`/api/deliveries/${date}`);
