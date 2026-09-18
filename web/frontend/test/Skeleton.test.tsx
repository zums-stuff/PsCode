import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { SkeletonText, SkeletonRow, SkeletonTable } from "../src/components/Skeleton";

describe("Skeleton", () => {
  it("SkeletonText renders with aria-hidden=true", () => {
    const { container } = render(<SkeletonText />);
    const el = container.querySelector(".skeleton-text");
    expect(el).toHaveAttribute("aria-hidden", "true");
  });

  it("SkeletonRow renders lines skeleton text spans", () => {
    const { container } = render(<SkeletonRow lines={4} />);
    const spans = container.querySelectorAll(".skeleton-text");
    expect(spans).toHaveLength(4);
  });

  it("SkeletonTable renders rows x cols cells", () => {
    const { container } = render(<SkeletonTable rows={3} cols={2} />);
    const rows = container.querySelectorAll("tr");
    expect(rows).toHaveLength(3);
    const cells = container.querySelectorAll("td");
    expect(cells).toHaveLength(6);
  });
});
