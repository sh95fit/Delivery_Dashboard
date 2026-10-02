const LABEL: Record<string, string> = { PREVIEW: "미리보기", LIVE: "진행 중", RESULT: "완료", NONE: "데이터 없음" };

export default function Badge({ state }: { state: string }) {
  const key = LABEL[state] ? state.toLowerCase() : "none";
  return <span className={`badge badge-${key}`}>{LABEL[state] ?? state}</span>;
}
