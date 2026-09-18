import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import ProblemsFilter from "../src/components/ProblemsFilter";
import type { Filters } from "../src/lib/types";

const baseFilters: Filters = {
  complexity: [],
  solved: "all",
  query: "",
};

describe("ProblemsFilter", () => {
  it("renders all complexity checkboxes and a search input", () => {
    const onChange = vi.fn();
    render(<ProblemsFilter value={baseFilters} onChange={onChange} />);

    expect(screen.getByTestId("problems-complexity-O(1)")).toBeInTheDocument();
    expect(screen.getByTestId("problems-complexity-O(log n)")).toBeInTheDocument();
    expect(screen.getByTestId("problems-complexity-O(n)")).toBeInTheDocument();
    expect(screen.getByTestId("problems-complexity-O(n log n)")).toBeInTheDocument();
    expect(screen.getByTestId("problems-complexity-O(n²)")).toBeInTheDocument();
    expect(screen.getByTestId("problems-complexity-O(n³)")).toBeInTheDocument();
    expect(screen.getByTestId("problems-complexity-O(2ⁿ)")).toBeInTheDocument();
    expect(screen.getByTestId("problems-complexity-other")).toBeInTheDocument();
    expect(screen.getByTestId("problems-search-input")).toBeInTheDocument();
  });

  it("clicking a complexity checkbox fires onChange with the updated array", () => {
    const onChange = vi.fn();
    render(<ProblemsFilter value={baseFilters} onChange={onChange} />);

    const onCheckbox = screen.getByTestId("problems-complexity-O(n)").querySelector("input")!;
    fireEvent.click(onCheckbox);

    expect(onChange).toHaveBeenCalledWith({
      ...baseFilters,
      complexity: ["O(n)"],
    });
  });

  it("typing in the search input fires onChange with the updated query", () => {
    const onChange = vi.fn();
    render(<ProblemsFilter value={baseFilters} onChange={onChange} />);

    const searchInput = screen.getByTestId("problems-search-input");
    fireEvent.change(searchInput, { target: { value: "suma" } });

    expect(onChange).toHaveBeenCalledWith({
      ...baseFilters,
      query: "suma",
    });
  });

  it("solved-status radio buttons fire onChange correctly when changed", () => {
    const onChange = vi.fn();
    render(<ProblemsFilter value={baseFilters} onChange={onChange} />);

    const solvedRadio = screen.getByTestId("problems-solved-solved").querySelector("input")!;
    fireEvent.click(solvedRadio);

    expect(onChange).toHaveBeenCalledWith({
      ...baseFilters,
      solved: "solved",
    });
  });
});
