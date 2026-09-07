/**
 * Journey (f) — Mobile viewport solve page (plan todo 42, line 451).
 *
 * The Solve page uses a 3-pane CSS grid on desktop (statement /
 * editor / results); on viewports <= 900px wide the grid collapses
 * to a single column (rules in routes/Solve.css:115-119).  This
 * journey runs in the "mobile" project (Pixel 5 viewport, 393x851)
 * and asserts:
 *   1. The grid is in single-column layout (1fr).
 *   2. The page has no horizontal overflow at 375px width.
 *   3. Each pane is reachable by scrolling — statement, editor,
 *      results all render in the stacked order.
 *   4. The editor mounts in CodeMirror and accepts typing.
 */

import { expect, test } from "@playwright/test";
import {
  appUrl,
  loginViaUi,
  SEED,
  typeIntoEditor,
} from "./_helpers";

const SUMA_PROBLEM_ID = 2;

test.describe("Journey (f) — mobile solve page", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("solve page is usable at 375px wide (no horizontal overflow, panes stack)", async ({
    page,
  }) => {
    await loginViaUi(page, SEED.student.username, SEED.student.password);

    await page.goto(appUrl(`/problem/${SUMA_PROBLEM_ID}`));
    await expect(page.locator(".solve-grid")).toBeVisible({ timeout: 15_000 });

    // The page body must not horizontally overflow at 375px.
    const overflow = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client + 1);

    // All three panes render and stack vertically.  In single-column
    // layout, the bounding boxes of statement / editor / results have
    // roughly equal widths and their left edges align.
    const statement = await page.locator(".solve-statement").boundingBox();
    const editor = await page.locator(".solve-editor").boundingBox();
    const results = await page.locator(".solve-results").boundingBox();
    expect(statement).not.toBeNull();
    expect(editor).not.toBeNull();
    expect(results).not.toBeNull();
    if (!statement || !editor || !results) throw new Error("pane bbox missing");

    // Vertical stacking: each pane's top is below the previous pane's
    // top, and widths are roughly equal (single column).
    expect(editor.y).toBeGreaterThan(statement.y);
    expect(results.y).toBeGreaterThan(editor.y);
    expect(Math.abs(editor.width - statement.width)).toBeLessThan(4);
    expect(Math.abs(results.width - editor.width)).toBeLessThan(4);

    // The toolbar (Run + Submit + Reset) wraps gracefully — buttons
    // remain visible without horizontal overflow.
    await expect(page.getByRole("button", { name: /Ejecutar muestra/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Enviar$/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Reiniciar/ })).toBeVisible();

    // The CodeMirror editor mounts and accepts typing.
    await typeIntoEditor(
      page,
      "Proceso Suma\n    Definir a, b: Entero\nFinProceso\n",
    );
    await expect(page.locator(".solve-editor-cm .cm-content")).toContainText(
      "Proceso Suma",
    );

    // Submit button still works at this width.
    await page.getByRole("button", { name: /^Enviar$/ }).click();
    // No overflow during/after submit either (the submit may end in a
    // network error if the API is unreachable from this viewport, but
    // the layout must not break).
    await page.waitForTimeout(500);
    const overflow2 = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(overflow2.scroll).toBeLessThanOrEqual(overflow2.client + 1);
  });
});
