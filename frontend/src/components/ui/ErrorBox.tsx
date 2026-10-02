// ErrorBox.tsx
export default function ErrorBox({ message }: { message: string }) {
  return <p className="error-box">오류: {message}</p>;
}
