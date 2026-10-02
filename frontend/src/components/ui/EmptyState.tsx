// EmptyState.tsx
export default function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {description && <div>{description}</div>}
    </div>
  );
}
