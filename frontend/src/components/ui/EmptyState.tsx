export default function EmptyState({ title, description }: { title: string; description?: string }) {
    return (
      <div
        style={{
          padding: "32px 20px",
          textAlign: "center",
          color: "#666",
          background: "#fff",
          border: "1px solid #eee",
          borderRadius: 12,
        }}
      >
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>{title}</div>
        {description && <div style={{ fontSize: 14 }}>{description}</div>}
      </div>
    );
  }
  