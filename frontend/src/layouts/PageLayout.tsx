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
    <div
      style={{
        width: "100%",
        maxWidth: "none",
        padding: "16px 20px 28px",
        fontFamily: "system-ui, sans-serif",
        boxSizing: "border-box",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 16,
          flexWrap: "wrap",
        }}
      >
        <h1 style={{ fontSize: 20, margin: 0 }}>{title}</h1>
        {right}
      </header>
      {children}
    </div>
  );
}
