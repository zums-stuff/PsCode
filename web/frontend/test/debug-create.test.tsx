import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

describe("debug", () => {
  it("logs calls", async () => {
    const calls: any[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ input: String(input), init });
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    });
    const { api } = await import("../src/lib/api");
    await api.post("/api/problems", { title: "X", is_public: false });
    console.log("CALLS:", JSON.stringify(calls));
  });
});
