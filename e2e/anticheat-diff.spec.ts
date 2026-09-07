/**
 * Journey (e) — Teacher anticheat report (plan todo 42, line 451).
 *
 * The seed plants a copy pair: two Fibonacci solutions (one each
 * from student01 and student02) with renamed identifiers
 * (a/b/c/i → previo/actual/siguiente/contador vs.
 * primero/segundo/acumulado/paso).  The anticheat engine's
 * normalization folds all identifiers → the pair scores 1.0 (well
 * above the 0.85 class default threshold).
 *
 * This journey:
 *   1. Logs in as the seeded teacher.
 *   2. Navigates to /admin/anticheat, picks scope=class, id=1
 *      (Class Alpha from the seed).
 *   3. The pairs table surfaces the planted pair at the top.
 *   4. Clicking "Ver diff" opens the side-by-side diff viewer with
 *      the ORIGINAL sources (no normalization leaks over the wire —
 *      plan §39 MUST NOT).
 */

import { expect, test } from "@playwright/test";
import { appUrl, loginViaUi, SEED } from "./_helpers";

const CLASS_ALPHA_ID = 1; // seed.py inserts one class first → id 1

test.describe("Journey (e) — teacher anticheat report", () => {
  test("planted pair appears at the top of the class report and the diff viewer loads", async ({
    page,
  }) => {
    await loginViaUi(page, SEED.teacher.username, SEED.teacher.password);

    await page.goto(appUrl("/admin/anticheat"));
    await expect(page.locator("h1")).toContainText(/Reporte de anticheat/i, {
      timeout: 15_000,
    });

    // Pick class scope + Class Alpha id (1) and apply.
    await page.locator("#anticheat-scope-kind").selectOption("class");
    await page.locator("#anticheat-scope-id").fill(String(CLASS_ALPHA_ID));
    await page.getByRole("button", { name: /Aplicar/ }).click();

    // Pairs table loads.  The planted pair (student01 vs student02
    // Fibonacci, score ~1.0) must be present.
    const pairsTable = page.locator(".anticheat-pair-list table");
    await expect(pairsTable).toBeVisible({ timeout: 30_000 });

    // Wait for at least one pair row to render.  Pair rows carry
    // data-testid={`pair-row-${run_a_id}-${run_b_id}`} per
    // AnticheatPairList.tsx.
    await expect(page.locator('[data-testid^="pair-row-"]').first()).toBeVisible(
      { timeout: 15_000 },
    );

    // The first row's similarity score is >= 0.85 (the threshold);
    // assert the visible formatted score is at least 0.8500.
    const firstScore = page
      .locator('[data-testid^="pair-row-"]')
      .first()
      .locator("td")
      .nth(2);
    const scoreText = (await firstScore.textContent()) ?? "";
    const score = Number.parseFloat(scoreText);
    expect(Number.isFinite(score)).toBeTruthy();
    expect(score).toBeGreaterThanOrEqual(0.85);

    // The planted pair mentions both student01 and student02.
    const firstRow = page.locator('[data-testid^="pair-row-"]').first();
    const rowText = (await firstRow.textContent()) ?? "";
    expect(rowText).toMatch(/student01|estudiante\s*01/i);
    expect(rowText).toMatch(/student02|estudiante\s*02/i);

    // Click "Ver diff" to open the side-by-side viewer.
    const diffResponse = page.waitForResponse(
      (res) =>
        res.url().includes("/api/admin/anticheat/pair/") && res.status() === 200,
      { timeout: 15_000 },
    );
    await firstRow.getByRole("button", { name: /Ver diff/ }).click();
    const res = await diffResponse;
    expect(res.status()).toBe(200);

    // The diff viewer renders both source panes with ORIGINAL sources.
    const viewer = page.getByTestId("anticheat-diff-viewer");
    await expect(viewer).toBeVisible({ timeout: 10_000 });

    const sourceA = viewer.locator('[data-side="a"] .cm-content');
    const sourceB = viewer.locator('[data-side="b"] .cm-content');
    await expect(sourceA).toBeVisible({ timeout: 5_000 });
    await expect(sourceB).toBeVisible({ timeout: 5_000 });

    // Both sources must contain the Proceso keyword + at least one
    // identifier distinct from the other (proving the originals came
    // through verbatim, not normalized).
    const aText = (await sourceA.textContent()) ?? "";
    const bText = (await sourceB.textContent()) ?? "";
    expect(aText).toContain("Proceso Fibonacci");
    expect(bText).toContain("Proceso Fibonacci");

    // Distinct identifier sets (rename survives): "previo" appears in
    // copy A, "primero" appears in copy B (per seed.py:FIBONACCI_COPY_*).
    expect(aText.toLowerCase()).toMatch(/previo/);
    expect(bText.toLowerCase()).toMatch(/primero/);
  });
});
