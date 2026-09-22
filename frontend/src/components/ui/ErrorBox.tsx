export default function ErrorBox({ message }: { message: string }) {
    return <p style={{ color: "#c62828", whiteSpace: "pre-wrap" }}>오류: {message}</p>;
  }
  