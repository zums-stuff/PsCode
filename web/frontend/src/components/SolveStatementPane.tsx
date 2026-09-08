import type { ProblemOut } from "../lib/types";
import Markdown from "./Markdown";

/** Read-only problem statement pane: title + markdown with pseint code blocks. */
export default function SolveStatementPane({ problem }: { problem: ProblemOut }) {
  return (
    <section className="solve-statement">
      <h2>{problem.title}</h2>
      <div className="markdown-preview">
        <Markdown source={problem.statement} />
      </div>
    </section>
  );
}