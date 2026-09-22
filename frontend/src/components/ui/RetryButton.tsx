export default function RetryButton({ onClick }: { onClick: () => void }) {
    return (
      <button
        type="button"
        onClick={onClick}
        style={{
          padding: "8px 12px",
          borderRadius: 8,
          border: "1px solid #ddd",
          background: "#fff",
          cursor: "pointer",
        }}
      >
        다시 시도
      </button>
    );
  }
  