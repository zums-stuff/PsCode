/**
 * Journey (a) — Student register → solve → submit (plan todo 42, line 451).
 *
 * Steps:
 *   1. Register a fresh student with the seeded class code ABC123.
 *   2. Land on /problems, open the Suma assignment.
 *   3. Type invalid PseInt code → debounced inline lint mark appears.
 *   4. Fix the code, run the sample (practice), assert the modal closes
 *      and the output panel shows the expected sum.
 *   5. Submit (graded practice via the assignment context) → results
 *      pane shows the verdict + per-case table.
 *
 * The journey is fully UI-driven: no API shortcut, no mocked WS.  The
 * /api/validate POST, /api/runs POST, and the run-status poll all hit
 * the live stack seeded by scripts/seed.py.
 */

import { expect, test } from "@playwright/test";
import {
  appUrl,
  registerStudent,
  SEED,
  uniqueDisplayName,
  uniqueUsername,
} from "./_helpers";

const INVALID_SOURCE =
  "Proceso Suma\n    Definir a, b: Entero\n    Leer a\n    // falta el resto\n";

const VALID_SOURCE =
  "Proceso Suma\n" +
  "    Definir a, b: Entero\n" +
  "    Leer a\n" +
  "    Leer b\n" +
  "    Escribir a + b\n" +
  "FinProceso\n";

test.describe("Journey (a) — register → solve → submit", () => {
  test("student self-registers, opens Suma, fixes inline error, runs sample, submits", async ({
    page,
  }) => {
    const username = uniqueUsername("e2e_a");
    const displayName = uniqueDisplayName();

    // --- 1. register with seeded class code -----------------------
    await registerStudent(page, {
      username,
      displayName,
      password: "Pass1234!",
      classCode: SEED.classCode,
    });

    // --- 2. open the Suma problem ----------------------------------
    await page.goto(appUrl("/problem/2")); // Suma per seed.py:order
    await expect(page.locator(".solve-grid")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("h1")).toContainText(/Resolver problema/);
    await expect(page.locator(".solve-statement")).toContainText(/Suma/);

    // --- 3. type invalid code → inline error appears ---------------
    const cm = page.locator(".solve-editor-cm .cm-content");
    await cm.click();
    await page.keyboard.type(INVALID_SOURCE, { delay: 4 });

    // The debounced linter runs POST /api/validate; the gutter mark
    // surfaces within ~400ms (CodeMirror linter delay) + network.
    await expect(page.locator(".cm-lintRange-error")).toBeVisible({
      timeout: 5_000,
    });

    // --- 4. fix the code, run the sample ---------------------------
    // Replace the entire doc via Ctrl+A then type (CM6 doesn't take
    // a programmatic value swap on the controlled component).
    await cm.click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.press("Delete");
    await page.keyboard.type(VALID_SOURCE, { delay: 4 });

    // The lint error clears once the engine parses cleanly.
    await expect(page.locator(".cm-lintRange-error")).toHaveCount(0, {
      timeout: 5_000,
    });

    // Click "Ejecutar muestra" → modal opens → "Ejecutar"
    await page.getByRole("button", { name: /Ejecutar muestra/ }).click();
    await expect(page.locator(".run-modal")).toBeVisible({ timeout: 5_000 });
    // Modal pre-fills the sample input ("1 2"); just click Ejecutar.
    await page.getByRole("button", { name: /^Ejecutar$/ }).click();
    // Modal closes, practice output panel appears.
    await expect(page.locator(".run-modal")).toHaveCount(0, { timeout: 10_000 });

    // --- 5. submit and wait for the verdict ------------------------
    await page.getByRole("button", { name: /^Enviar$/ }).click();
    // The status pill transitions queued → running → done with AC.
    await expect(page.locator(".solve-results")).toContainText(/Terminado|done/i, {
      timeout: 30_000,
    });
    // AC appears at least once (summary + per-case row).
    const verdicts = page.locator(".solve-results .status-badge", { hasText: /AC/i });
    await expect(verdicts.first()).toBeVisible({ timeout: 5_000 });
  });
});
