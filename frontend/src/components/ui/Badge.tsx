const COLORS: Record<string, string> = {
    PREVIEW: "#8b8b00",
    LIVE: "#c62828",
    RESULT: "#2e7d32",
    NONE: "#9e9e9e",
  };
  
  const LABEL: Record<string, string> = {
    PREVIEW: "미리보기",
    LIVE: "진행 중",
    RESULT: "완료",
    NONE: "데이터 없음",
  };
  
  export default function Badge({ state }: { state: string }) {
    return (
      <span
        style={{
          background: COLORS[state] ?? "#999",
          color: "#fff",
          padding: "4px 10px",
          borderRadius: 999,
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        {LABEL[state] ?? state}
      </span>
    );
  }
  