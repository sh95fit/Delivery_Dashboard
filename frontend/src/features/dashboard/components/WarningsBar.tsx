import Chip from "@/components/ui/Chip";
import type { ChipTone } from "@/components/ui/Chip";
import type { DayWarnings } from "@/api/types";
import { num } from "@/lib/format";

const SRC_LABEL: Record<string, string> = { web: "웹", admin: "어드민", app: "앱" };

export default function WarningsBar({ warnings }: { warnings?: DayWarnings | null }) {
  if (!warnings) return null;
  const w = warnings;
  const n = (v?: number | null) => v ?? 0;
  const chips: { key: string; tone: ChipTone; text: string }[] = [];

  if (n(w.cancelled_orders) > 0) {
    const bySrc = Object.entries(w.cancelled_by_source ?? {})
      .map(([k, v]) => `${SRC_LABEL[k] ?? k} ${v.orders}건`)
      .join(" · ");
    const lost = n(w.cancelled_stops) > 0 ? ` (배송지 소멸 ${num(w.cancelled_stops)}곳)` : "";
    chips.push({
      key: "cancel", tone: "neutral",
      text: `주문 취소 ${num(w.cancelled_orders)}건 · ${num(w.cancelled_qty)}식${lost}${bySrc ? ` — ${bySrc}` : ""}`,
    });
  }
  if (n(w.unconverted_app_qty) > 0)
    chips.push({ key: "unconv", tone: "neutral", text: `마감 후 앱 미전환 ${num(w.unconverted_app_qty)}식 (합계 제외)` });
  if (n(w.insufficient_records) > 0)
    chips.push({ key: "insuf", tone: "neutral", text: `최소수량 미달 기록 ${num(w.insufficient_records)}건` });
  if (n(w.app_unmatched_address_qty) > 0)
    chips.push({ key: "addr", tone: "caution", text: `앱 선택 배송지 매칭 실패 ${num(w.app_unmatched_address_qty)}식 (합계 제외)` });
  if (n(w.app_unmapped_product_qty) > 0)
    chips.push({ key: "prod", tone: "caution", text: `앱 선택 중 라인업 외 상품 ${num(w.app_unmapped_product_qty)}식 (합계 제외)` });
  if (n(w.app_blocked_qty) > 0)
    chips.push({ key: "block", tone: "caution", text: `앱 차단 상품 선택 ${num(w.app_blocked_qty)}식 (합계 제외)` });
  if (n(w.unplaced_qty) > 0)
    chips.push({ key: "unplaced", tone: "caution", text: `배송지 없는 주문 ${num(w.unplaced_lines)}건 · ${num(w.unplaced_qty)}식 (합계 제외)` });
  if (n(w.no_coord_stops) > 0)
    chips.push({ key: "coord", tone: "caution", text: `좌표 없는 배송지 ${num(w.no_coord_stops)}곳 (지도 미표시, 합계 포함)` });

  if (chips.length === 0) return null;
  return (
    <div className="chips">
      {chips.map((c) => <Chip key={c.key} tone={c.tone}>{c.text}</Chip>)}
    </div>
  );
}
