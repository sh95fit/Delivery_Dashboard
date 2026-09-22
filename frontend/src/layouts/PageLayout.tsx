import type { ReactNode } from "react";

export default function PageLayout({
  title,
  children,
  right,
}: {
  title: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div style={{ maxWidth: 1080, margin: "0 auto", padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, margin: 0 }}>{title}</h1>
        {right}
      </header>
      {children}
    </div>
  );
}
