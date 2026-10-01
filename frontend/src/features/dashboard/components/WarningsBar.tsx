import type { DayWarnings } from "@/api/types";
import { num } from "@/lib/format";

type Chip = { key: string; tone: "info" | "warn"; text: string };

const SRC_LABEL: Record<string, string> = { web: "웹", admin: "어드민", app: "앱" };
const TONE = {
  info: { background: "#f1f5f9", color: "#334155", border: "1px solid #e2e8f0" },
  warn: { background: "#fff7ed", color: "#9a3412", border: "1px solid #fed7aa" },
};

export default function WarningsBar({ warnings }: { warnings?: DayWarnings | null }) {
  if (!warnings) return null;
  const w = warnings;
  const n = (v?: number | null) => v ?? 0;
  const chips: Chip[] = [];

  if (n(w.cancelled_orders) > 0) {
    const bySrc = Object.entries(w.cancelled_by_source ?? {})
      .map(([k, v]) => `${SRC_LABEL[k] ?? k} ${v.orders}건`)
      .join(" · ");
    const lost = n(w.cancelled_stops) > 0 ? ` (배송지 소멸 ${num(w.cancelled_stops)}곳)` : "";
    chips.push({
      key: "cancel",
      tone: "info",
      text: `주문 취소 ${num(w.cancelled_orders)}건 · ${num(w.cancelled_qty)}식${lost}${bySrc ? ` — ${bySrc}` : ""}`,
    });
  }
  if (n(w.unconverted_app_qty) > 0)
    chips.push({ key: "unconv", tone: "info", text: `마감 후 앱 미전환 ${num(w.unconverted_app_qty)}식 (합계 제외)` });
  if (n(w.insufficient_records) > 0)
    chips.push({ key: "insuf", tone: "info", text: `최소수량 미달 기록 ${num(w.insufficient_records)}건` });
  if (n(w.app_unmatched_address_qty) > 0)
    chips.push({ key: "addr", tone: "warn", text: `앱 선택 배송지 매칭 실패 ${num(w.app_unmatched_address_qty)}식 (합계 제외)` });
  if (n(w.app_unmapped_product_qty) > 0)
    chips.push({ key: "prod", tone: "warn", text: `앱 선택 중 라인업 외 상품 ${num(w.app_unmapped_product_qty)}식 (합계 제외)` });
  if (n(w.app_blocked_qty) > 0)
    chips.push({ key: "block", tone: "warn", text: `앱 차단 상품 선택 ${num(w.app_blocked_qty)}식 (합계 제외)` });
  if (n(w.unplaced_qty) > 0)
    chips.push({ key: "unplaced", tone: "warn", text: `배송지 없는 주문 ${num(w.unplaced_lines)}건 · ${num(w.unplaced_qty)}식 (합계 제외)` });
  if (n(w.no_coord_stops) > 0)
    chips.push({ key: "coord", tone: "warn", text: `좌표 없는 배송지 ${num(w.no_coord_stops)}곳 (지도 미표시, 합계 포함)` });

  if (chips.length === 0) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
      {chips.map((c) => (
        <span key={c.key} style={{ ...TONE[c.tone], borderRadius: 8, padding: "6px 10px", fontSize: 12, fontWeight: 600 }}>
          {c.text}
        </span>
      ))}
    </div>
  );
}
