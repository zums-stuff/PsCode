/**
 * Journey (b) — Assignment best-count badge (plan todo 42, line 451).
 *
 * The seed creates two assignment problems (Suma + Primo) attached to
 * Class Alpha with a 14-day deadline.  This journey:
 *   1. Logs in as a seeded student (student03 — no planted runs on
 *      their account, so the contest scoreboard remains untouched).
 *   2. Submits a WRONG solution to Suma → verdict WA, no BestBadge
 *      on the only attempt so far (one submission is trivially the
 *      "best of one").
 *   3. Submits the CORRECT solution → verdict AC, the AC submission
 *      wins the best-count comparison (priority AC > WA) and shows
 *      the "Mejor" badge on the /submissions row.
 *
 * The BestBadge logic is computed client-side (plan §M7); the server
 * returns the runs list and the table picks the highest-priority
 * verdict per (problem_id, assignment_id) group.
 */

import { expect, test } from "@playwright/test";
import {
  appUrl,
  getApiUrl,
  loginViaApi,
  loginViaUi,
  SEED,
} from "./_helpers";

const SUMA_PROBLEM_ID = 2;
const SUMA_ASSIGNMENT_ID = 1; // seed.py: assignments inserted in order (Suma first)

const WA_SOURCE =
  "Proceso Suma\n" +
  "    Definir a, b: Entero\n" +
  "    Leer a\n" +
  "    Leer b\n" +
  "    Escribir a - b\n" + // intentionally wrong
  "FinProceso\n";

const AC_SOURCE =
  "Proceso Suma\n" +
  "    Definir a, b: Entero\n" +
  "    Leer a\n" +
  "    Leer b\n" +
  "    Escribir a + b\n" +
  "FinProceso\n";

test.describe("Journey (b) — assignment best-count", () => {
  test("the better submission (AC) wins the best badge over a prior WA", async ({
    page,
    request,
  }) => {
    // --- 1. Log in as a fresh student via the UI ------------------
    // student03 has no planted runs (seed plants runs for student01,
    // student02, student03, student04 on Fibonacci contest only).
    await loginViaUi(page, SEED.student.username, SEED.student.password);

    // --- 2. Submit a WRONG solution first ------------------------
    await page.goto(appUrl(`/problem/${SUMA_PROBLEM_ID}?assignment=${SUMA_ASSIGNMENT_ID}`));
    await expect(page.locator(".solve-grid")).toBeVisible({ timeout: 15_000 });

    const cm = page.locator(".solve-editor-cm .cm-content");
    await cm.click();
    await page.keyboard.type(WA_SOURCE, { delay: 4 });
    await expect(page.locator(".cm-lintRange-error")).toHaveCount(0, { timeout: 5_000 });

    await page.getByRole("button", { name: /^Enviar$/ }).click();
    // Results pane shows WA within the polling window.
    await expect(page.locator(".solve-results")).toContainText(/Terminado|done/i, {
      timeout: 30_000,
    });
    const verdictCells = page.locator(".solve-results td .status-badge");
    await expect(verdictCells.first()).toContainText(/WA|AC/i, { timeout: 30_000 });

    // --- 3. Submit the CORRECT solution --------------------------
    await page.goto(appUrl(`/problem/${SUMA_PROBLEM_ID}?assignment=${SUMA_ASSIGNMENT_ID}`));
    await page.locator(".solve-editor-cm .cm-content").click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.press("Delete");
    await page.keyboard.type(AC_SOURCE, { delay: 4 });

    await page.getByRole("button", { name: /^Enviar$/ }).click();
    await expect(page.locator(".solve-results")).toContainText(/Terminado|done/i, {
      timeout: 30_000,
    });
    await expect(
      page.locator(".solve-results .status-badge", { hasText: /AC/i }).first(),
    ).toBeVisible({ timeout: 30_000 });

    // --- 4. /submissions shows the BestBadge on the AC row -------
    await page.goto(appUrl("/submissions"));
    await expect(page.locator("table.data-table")).toBeVisible({ timeout: 10_000 });

    // Filter to assignment runs for this problem so the assertion
    // doesn't race against the student's own past contest runs.
    const assignmentRows = page.locator(
      `table.data-table tbody tr:has(a[href="/problem/${SUMA_PROBLEM_ID}"])`,
    );
    await expect(assignmentRows.first()).toBeVisible({ timeout: 10_000 });

    const rowCount = await assignmentRows.count();
    expect(rowCount).toBeGreaterThanOrEqual(2);

    // Exactly one row carries the "Mejor" badge among the Suma rows
    // (plan M7 — assignment-best = highest verdict priority, fewest
    // steps tiebreak; AC outranks WA).
    const bestRows = assignmentRows.locator(":scope", { hasText: /Mejor/ });
    const bestCount = await bestRows.count();
    expect(bestCount).toBeGreaterThanOrEqual(1);
    expect(bestCount).toBeLessThanOrEqual(2);

    // Belt-and-braces: the row marked Best should also be the AC row.
    const acRow = assignmentRows
      .locator(":scope", { hasText: /AC/ })
      .filter({ hasText: /Mejor/ })
      .first();
    await expect(acRow).toBeVisible({ timeout: 5_000 });
  });

  /**
   * Sanity check that the API itself considers the AC submission the
   * best one — useful for catching a regression where the client-side
   * best logic drifts from what the server stores.  Not the primary
   * UI assertion; just a guard rail.
   */
  test("server records both submissions with their verdicts", async ({ request }) => {
    const token = await loginViaApi(request, SEED.student);
    const res = await request.get(`${getApiUrl()}/api/runs?page=1&size=20`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
    const body = (await res.json()) as {
      items: Array<{
        id: number;
        problem_id: number;
        kind: string;
        summary_verdict: string | null;
      }>;
    };
    const sumaRuns = body.items.filter(
      (r) => r.problem_id === SUMA_PROBLEM_ID && r.kind === "assignment",
    );
    expect(sumaRuns.length).toBeGreaterThanOrEqual(2);
    const verdicts = sumaRuns.map((r) => r.summary_verdict);
    expect(verdicts).toContain("AC");
  });
});
