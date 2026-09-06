import type { ProblemOut } from "../lib/types";
import { renderMarkdown } from "./StatementEditor";

/** Read-only problem statement pane: title + markdown with pseint code blocks. */
export default function SolveStatementPane({ problem }: { problem: ProblemOut }) {
  return (
    <section className="solve-statement">
      <h2>{problem.title}</h2>
      <div className="markdown-preview">{renderMarkdown(problem.statement)}</div>
    </section>
  );
}