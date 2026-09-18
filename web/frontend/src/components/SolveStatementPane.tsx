import type { ProblemOut } from "../lib/types";
import Markdown from "./Markdown";

interface Section {
  heading: string | null;
  body: string;
}

const SECTION_RE =
  /^#{1,3}\s+(Input|Output|Examples?|Nota|Note|Constraints?|Restricciones?|Entrada|Salida|Descripción|Description)\s*$/gim;

function splitSections(source: string): Section[] {
  const sections: Section[] = [];
  let lastIndex = 0;
  let lastHeading: string | null = null;
  const re = new RegExp(SECTION_RE.source, SECTION_RE.flags);
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    if (m.index > lastIndex || sections.length === 0) {
      sections.push({
        heading: lastHeading,
        body: source.slice(lastIndex, m.index).trim(),
      });
    }
    lastHeading = m[1];
    lastIndex = m.index + m[0].length;
  }
  sections.push({
    heading: lastHeading,
    body: source.slice(lastIndex).trim(),
  });
  return sections.filter((s) => s.body.length > 0 || s.heading !== null);
}

function sectionClass(heading: string | null): string {
  if (!heading) return "cf-section";
  const h = heading.toLowerCase();
  if (h === "nota" || h === "note") return "cf-section cf-note";
  if (h === "constraints?" || h === "restricciones?") return "cf-section cf-constraints";
  return "cf-section";
}

function ExamplePairs({ body }: { body: string }) {
  const pairs: { input: string; output: string }[] = [];
  const lines = body.split("\n");
  let current: { input: string; output: string } | null = null;
  let mode: "input" | "output" | null = null;
  for (const line of lines) {
    const trimmed = line.trim();
    if (/^input\s*$/i.test(trimmed)) {
      if (current && mode === "output") {
        pairs.push(current);
      }
      current = { input: "", output: "" };
      mode = "input";
      continue;
    }
    if (/^output\s*$/i.test(trimmed)) {
      mode = "output";
      continue;
    }
    if (current && mode === "input") {
      current.input += (current.input ? "\n" : "") + line;
    } else if (current && mode === "output") {
      current.output += (current.output ? "\n" : "") + line;
    }
  }
  if (current && mode === "output") {
    pairs.push(current);
  }
  if (pairs.length === 0) {
    return <Markdown source={body} />;
  }
  return (
    <div className="cf-examples">
      {pairs.map((p, i) => (
        <div key={i} className="cf-example-pair">
          <div className="cf-example-col">
            <div className="cf-example-label">Input</div>
            <pre className="cf-example-pre">{p.input}</pre>
          </div>
          <div className="cf-example-col">
            <div className="cf-example-label">Output</div>
            <pre className="cf-example-pre">{p.output}</pre>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Read-only problem statement pane: Codeforces-style sectioned rendering.
 * Parses ### Input / ### Output / ### Examples / ### Note / ### Constraints
 * headers and renders each with appropriate typography. Falls back to plain
 * markdown when no section headers are detected.
 */
export default function SolveStatementPane({ problem }: { problem: ProblemOut }) {
  const sections = splitSections(problem.statement);
  const hasSections = sections.length > 1 || (sections.length === 1 && sections[0].heading !== null);

  return (
    <section className="solve-statement">
      <h2>{problem.title}</h2>
      <div className="markdown-preview">
        {!hasSections ? (
          <Markdown source={problem.statement} />
        ) : (
          sections.map((sec, i) => {
            const isExamples =
              sec.heading !== null &&
              /^examples?$/i.test(sec.heading);
            return (
              <div key={i} className={sectionClass(sec.heading)}>
                {sec.heading !== null && (
                  <h3 className="cf-section-heading">{sec.heading}</h3>
                )}
                {isExamples ? (
                  <ExamplePairs body={sec.body} />
                ) : (
                  <Markdown source={sec.body} />
                )}
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
