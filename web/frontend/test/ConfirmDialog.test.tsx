import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import ConfirmDialog from "../src/components/ConfirmDialog";

describe("ConfirmDialog", () => {
  it("renders nothing when open=false", () => {
    const { container } = render(
      <ConfirmDialog
        open={false}
        title="Test"
        message="Message"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders the title and message when open=true", () => {
    render(
      <ConfirmDialog
        open={true}
        title="Delete item?"
        message="This action cannot be undone."
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByText("Delete item?")).toBeInTheDocument();
    expect(screen.getByText("This action cannot be undone.")).toBeInTheDocument();
  });

  it("pressing Escape calls onCancel", () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        title="Test"
        message="Message"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });

  it("clicking confirm calls onConfirm", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        title="Test"
        message="Message"
        confirmLabel="Yes"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("Yes"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("clicking the backdrop calls onCancel", () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        title="Test"
        message="Message"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    const backdrop = screen.getByRole("presentation");
    fireEvent.click(backdrop);
    expect(onCancel).toHaveBeenCalled();
  });
});
