import { t } from "../lib/i18n";

export interface TestCaseDraft {
  /** Present when the case already exists server-side. */
  id?: number;
  input: string;
  expected_output: string;
  seed: number;
  points: number;
  order: number;
  is_sample: boolean;
}

interface TestCaseTableProps {
  cases: TestCaseDraft[];
  onChange: (cases: TestCaseDraft[]) => void;
}

/** Editable test-case rows: input, expected output, points, seed, order, sample. */
export default function TestCaseTable({ cases, onChange }: TestCaseTableProps) {
  function update(index: number, patch: Partial<TestCaseDraft>) {
    onChange(cases.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  function remove(index: number) {
    onChange(cases.filter((_, i) => i !== index));
  }

  function add() {
    onChange([
      ...cases,
      {
        input: "",
        expected_output: "",
        seed: 0,
        points: 1,
        order: cases.length,
        is_sample: false,
      },
    ]);
  }

  return (
    <div className="test-case-table">
      <table>
        <thead>
          <tr>
            <th>{t("admin.problem.fields.case.input")}</th>
            <th>{t("admin.problem.fields.case.expected")}</th>
            <th>{t("admin.problem.fields.case.points")}</th>
            <th>{t("admin.problem.fields.case.seed")}</th>
            <th>{t("admin.problem.fields.case.order")}</th>
            <th>{t("admin.problem.fields.case.sample")}</th>
            <th aria-label={t("admin.problem.removeCase")} />
          </tr>
        </thead>
        <tbody>
          {cases.map((c, i) => (
            <tr key={c.id ?? `new-${i}`}>
              <td>
                <textarea
                  aria-label={`${t("admin.problem.fields.case.input")} ${i + 1}`}
                  value={c.input}
                  onChange={(e) => update(i, { input: e.target.value })}
                  rows={2}
                />
              </td>
              <td>
                <textarea
                  aria-label={`${t("admin.problem.fields.case.expected")} ${i + 1}`}
                  value={c.expected_output}
                  onChange={(e) => update(i, { expected_output: e.target.value })}
                  rows={2}
                />
              </td>
              <td>
                <input
                  type="number"
                  aria-label={`${t("admin.problem.fields.case.points")} ${i + 1}`}
                  value={c.points}
                  onChange={(e) => update(i, { points: Number(e.target.value) })}
                />
              </td>
              <td>
                <input
                  type="number"
                  aria-label={`${t("admin.problem.fields.case.seed")} ${i + 1}`}
                  value={c.seed}
                  onChange={(e) => update(i, { seed: Number(e.target.value) })}
                />
              </td>
              <td>
                <input
                  type="number"
                  aria-label={`${t("admin.problem.fields.case.order")} ${i + 1}`}
                  value={c.order}
                  onChange={(e) => update(i, { order: Number(e.target.value) })}
                />
              </td>
              <td>
                <input
                  type="checkbox"
                  aria-label={`${t("admin.problem.fields.case.sample")} ${i + 1}`}
                  checked={c.is_sample}
                  onChange={(e) => update(i, { is_sample: e.target.checked })}
                />
              </td>
              <td>
                <button
                  type="button"
                  className="danger"
                  onClick={() => remove(i)}
                >
                  {t("admin.problem.removeCase")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="add-row" onClick={add}>
        {t("admin.problem.addCase")}
      </button>
    </div>
  );
}