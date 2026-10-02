// RetryButton.tsx
import Button from "./Button";

export default function RetryButton({ onClick }: { onClick: () => void }) {
  return <Button onClick={onClick}>다시 시도</Button>;
}
