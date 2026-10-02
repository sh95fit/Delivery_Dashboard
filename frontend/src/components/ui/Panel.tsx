import type { ReactNode } from "react";

type Props = { title?: ReactNode; desc?: ReactNode; right?: ReactNode; tone?: "internal"; children: ReactNode };

export default function Panel({ title, desc, right, tone, children }: Props) {
  return (
    <section className={`panel${tone ? ` panel-${tone}` : ""}`}>
      {(title || right) && (
        <div className="panel-head">
          {title && <h2 className="panel-title">{title}</h2>}
          {right && <div className="panel-right">{right}</div>}
        </div>
      )}
      {desc && <p className="panel-desc">{desc}</p>}
      {children}
    </section>
  );
}
