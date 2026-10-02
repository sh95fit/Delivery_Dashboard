import type { ReactNode } from "react";

export default function Card({ title, children, sub }: { title: ReactNode; children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-title">{title}</div>
      <div className="stat-value">{children}</div>
      {sub ? <div className="stat-sub">{sub}</div> : null}
    </div>
  );
}
