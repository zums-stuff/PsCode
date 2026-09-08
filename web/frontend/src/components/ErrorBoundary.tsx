import { Component, type ErrorInfo, type ReactNode } from "react";
import { t } from "../lib/i18n";

/**
 * Top-level error boundary (contest page fix). A render exception anywhere
 * below this boundary used to unmount the whole React tree → blank page.
 * Now it swaps in a friendly message instead, so a runtime crash never
 * blanks the UI silently.
 */
interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("ErrorBoundary caught:", error, info);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="error-boundary" data-testid="error-boundary">
          <p className="error">{t("error.unexpected")}</p>
        </div>
      );
    }
    return this.props.children;
  }
}