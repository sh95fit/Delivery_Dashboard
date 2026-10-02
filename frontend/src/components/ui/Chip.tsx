import type { ReactNode } from "react";

export type ChipTone = "neutral" | "warn" | "caution" | "ok" | "danger" | "internal";

export default function Chip({ tone = "neutral", children, title }: { tone?: ChipTone; children: ReactNode; title?: string }) {
  return <span className={`chip chip-${tone}`} title={title}>{children}</span>;
}
