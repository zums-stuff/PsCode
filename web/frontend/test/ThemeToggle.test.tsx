import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import ThemeToggle from "../src/components/ThemeToggle";
import { ThemeProvider } from "../src/lib/theme";

function renderToggle(compact = false) {
  return render(
    <ThemeProvider>
      <ThemeToggle compact={compact} />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("ThemeToggle", () => {
  it("renders the three options with i18n labels", () => {
    renderToggle();
    expect(screen.getByText("Claro")).toBeInTheDocument();
    expect(screen.getByText("Oscuro")).toBeInTheDocument();
    expect(screen.getByText("Sistema")).toBeInTheDocument();
  });

  it("clicking Light sets data-theme to light and persists to localStorage", () => {
    renderToggle();
    const lightBtn = screen.getByTitle(/Claro/);
    fireEvent.click(lightBtn);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("pseint:theme")).toBe("light");
  });

  it("clicking Dark sets data-theme to dark", () => {
    renderToggle();
    const darkBtn = screen.getByTitle(/Oscuro/);
    fireEvent.click(darkBtn);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("pseint:theme")).toBe("dark");
  });

  it("the currently-active option has aria-checked=true", () => {
    renderToggle();
    const lightBtn = screen.getByTitle(/Claro/);
    fireEvent.click(lightBtn);
    expect(lightBtn.getAttribute("aria-checked")).toBe("true");
    const darkBtn = screen.getByTitle(/Oscuro/);
    expect(darkBtn.getAttribute("aria-checked")).toBe("false");
  });

  it("compact prop hides the labels (only icons visible)", () => {
    renderToggle(true);
    expect(screen.queryByText("Claro")).not.toBeInTheDocument();
    expect(screen.queryByText("Oscuro")).not.toBeInTheDocument();
    expect(screen.queryByText("Sistema")).not.toBeInTheDocument();
    const buttons = screen.getAllByRole("radio");
    expect(buttons).toHaveLength(3);
  });
});
