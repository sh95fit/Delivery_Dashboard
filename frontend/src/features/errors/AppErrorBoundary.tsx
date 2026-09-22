import React from "react";

interface State {
  hasError: boolean;
}

export default class AppErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  constructor(props: React.PropsWithChildren) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("AppErrorBoundary", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, textAlign: "center" }}>
          <h1>화면 오류가 발생했습니다</h1>
          <p>페이지를 새로고침하거나 잠시 후 다시 시도해 주세요.</p>
        </div>
      );
    }
    return this.props.children;
  }
}
