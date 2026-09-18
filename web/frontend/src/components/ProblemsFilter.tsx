import type { Filters } from "../lib/types";

const COMPLEXITIES = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)", "O(n³)", "O(2ⁿ)", "other"];

interface Props {
  value: Filters;
  onChange: (v: Filters) => void;
}

export default function ProblemsFilter({ value, onChange }: Props) {
  const toggleComplexity = (c: string) => {
    const next = value.complexity.includes(c)
      ? value.complexity.filter((x) => x !== c)
      : [...value.complexity, c];
    onChange({ ...value, complexity: next });
  };

  return (
    <div className="problems-filter roundbox sidebox" data-testid="problems-filter">
      <div className="problems-filter-section">
        <div className="problems-filter-label">Complejidad</div>
        <div className="problems-filter-row">
          {COMPLEXITIES.map((c) => (
            <label
              key={c}
              className="problems-filter-chip"
              data-testid={`problems-complexity-${c}`}
            >
              <input
                type="checkbox"
                checked={value.complexity.includes(c)}
                onChange={() => toggleComplexity(c)}
              />
              {c}
            </label>
          ))}
        </div>
      </div>

      <div className="problems-filter-section">
        <div className="problems-filter-label">Estado</div>
        <div className="problems-filter-row">
          {(["all", "solved", "unsolved"] as const).map((s) => (
            <label
              key={s}
              className="problems-filter-chip"
              data-testid={`problems-solved-${s}`}
            >
              <input
                type="radio"
                name="problems-solved-status"
                checked={value.solved === s}
                onChange={() => onChange({ ...value, solved: s })}
              />
              {s === "all" ? "Todos" : s === "solved" ? "Resueltos" : "No resueltos"}
            </label>
          ))}
        </div>
      </div>

      <div className="problems-filter-section">
        <div className="problems-filter-label">Buscar</div>
        <input
          type="text"
          className="problems-filter-search"
          placeholder="Buscar problema por nombre..."
          value={value.query}
          data-testid="problems-search-input"
          onChange={(e) => onChange({ ...value, query: e.target.value })}
        />
      </div>
    </div>
  );
}
