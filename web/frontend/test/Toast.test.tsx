import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { ToastProvider, useToast } from "../src/lib/toast";

function ToastTrigger({ kind }: { kind: "success" | "error" | "info" | "warning" }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => toast[kind](`Test ${kind} message`)}
    >
      Trigger {kind}
    </button>
  );
}

function renderWithProvider(ui: React.ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Toast", () => {
  it("useToast() outside a provider returns a graceful fallback (no crash)", () => {
    function FallbackTest() {
      const toast = useToast();
      expect(toast.toasts).toEqual([]);
      expect(typeof toast.success).toBe("function");
      return <div>ok</div>;
    }
    render(<FallbackTest />);
    expect(screen.getByText("ok")).toBeInTheDocument();
  });

  it("inside a ToastProvider, calling success() adds a toast with kind=success", () => {
    renderWithProvider(<ToastTrigger kind="success" />);
    fireEvent.click(screen.getByText("Trigger success"));
    expect(screen.getByTestId("toast-success")).toBeInTheDocument();
    expect(screen.getByText("Test success message")).toBeInTheDocument();
  });

  it("error() adds one with kind=error", () => {
    renderWithProvider(<ToastTrigger kind="error" />);
    fireEvent.click(screen.getByText("Trigger error"));
    expect(screen.getByTestId("toast-error")).toBeInTheDocument();
    expect(screen.getByText("Test error message")).toBeInTheDocument();
  });

  it("multiple toasts stack (rendered in order)", () => {
    function MultiTrigger() {
      const toast = useToast();
      return (
        <button
          type="button"
          onClick={() => {
            toast.success("First");
            toast.error("Second");
            toast.info("Third");
          }}
        >
          Trigger all
        </button>
      );
    }
    renderWithProvider(<MultiTrigger />);
    fireEvent.click(screen.getByText("Trigger all"));
    expect(screen.getByTestId("toast-success")).toBeInTheDocument();
    expect(screen.getByTestId("toast-error")).toBeInTheDocument();
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
    expect(screen.getByText("Third")).toBeInTheDocument();
  });

  it("clicking the close button dismisses the toast", () => {
    renderWithProvider(<ToastTrigger kind="success" />);
    fireEvent.click(screen.getByText("Trigger success"));
    expect(screen.getByTestId("toast-success")).toBeInTheDocument();
    const closeBtn = screen.getByLabelText("Cerrar");
    fireEvent.click(closeBtn);
    expect(screen.queryByTestId("toast-success")).not.toBeInTheDocument();
  });
});
