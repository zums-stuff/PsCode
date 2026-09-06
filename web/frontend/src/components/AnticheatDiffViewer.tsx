import { useEffect, useMemo, useRef } from "react";
import { Decoration, EditorView } from "@codemirror/view";
import {
  EditorState,
  RangeSetBuilder,
  StateField,
  type Extension,
  type RangeSet,
} from "@codemirror/state";
import { syntaxHighlighting } from "@codemirror/language";
import { pseint, pseintHighlightStyle } from "@codemirror/lang-pseint";
import { useQuery } from "@tanstack/react-query";
import { getAnticheatPair } from "../lib/api";
import type { AnticheatPair, AnticheatPairDetail } from "../lib/types";
import { t } from "../lib/i18n";

interface AnticheatDiffViewerProps {
  pair: AnticheatPair | null;
  onClose: () => void;
}

/**
 * /admin/anticheat pair-diff panel (todo 25 / plan §D13).
 *
 * Renders the ORIGINAL sources (verbatim — the server never exposes the
 * D13 normalization internals, plan §39 MUST NOT) side-by-side, with
 * tokens that don't appear in the *other* source highlighted via
 * CodeMirror decorations.  The comparison is purely visual: a token is
 * considered "different" when it is absent from the other source's
 * token set (split on whitespace).
 */
export default function AnticheatDiffViewer({
  pair,
  onClose,
}: AnticheatDiffViewerProps) {
  const enabled = pair !== null;
  const pairId =
    pair === null
      ? "0-0"
      : `${Math.min(pair.run_a_id, pair.run_b_id)}-${Math.max(
          pair.run_a_id,
          pair.run_b_id,
        )}`;
  const query = useQuery<AnticheatPairDetail>({
    queryKey: ["admin", "anticheat", "pair", pairId],
    queryFn: () =>
      getAnticheatPair(
        Math.min(pair!.run_a_id, pair!.run_b_id),
        Math.max(pair!.run_a_id, pair!.run_b_id),
      ),
    enabled,
  });

  if (!enabled) return null;

  if (query.isLoading) {
    return (
      <section className="anticheat-diff-viewer">
        <header>
          <h3>{t("admin.anticheat.diff.title")}</h3>
          <button type="button" onClick={onClose}>
            {t("admin.anticheat.diff.close")}
          </button>
        </header>
        <p>{t("admin.anticheat.diff.loading")}</p>
      </section>
    );
  }

  if (query.isError || query.data === undefined) {
    return (
      <section className="anticheat-diff-viewer">
        <header>
          <h3>{t("admin.anticheat.diff.title")}</h3>
          <button type="button" onClick={onClose}>
            {t("admin.anticheat.diff.close")}
          </button>
        </header>
        <p className="error">{t("admin.anticheat.diff.error")}</p>
      </section>
    );
  }

  const detail = query.data;

  return (
    <section
      className="anticheat-diff-viewer"
      data-testid="anticheat-diff-viewer"
    >
      <header>
        <h3>
          {t("admin.anticheat.diff.title")}{" "}
          <span className="hint">
            #{detail.run_a.id} ({detail.run_a.username}) ↔ #
            {detail.run_b.id} ({detail.run_b.username}) · score{" "}
            {detail.score.toFixed(4)}
            {detail.flagged ? ` · ${t("admin.anticheat.diff.flagged")}` : ""}
          </span>
        </h3>
        <button type="button" onClick={onClose}>
          {t("admin.anticheat.diff.close")}
        </button>
      </header>
      <div className="anticheat-diff-grid">
        <DiffSourceView
          label={`${t("admin.anticheat.diff.sourceA")} · #${detail.run_a.id} (${detail.run_a.username})`}
          source={detail.source_a}
          otherSource={detail.source_b}
          side="a"
        />
        <DiffSourceView
          label={`${t("admin.anticheat.diff.sourceB")} · #${detail.run_b.id} (${detail.run_b.username})`}
          source={detail.source_b}
          otherSource={detail.source_a}
          side="b"
        />
      </div>
    </section>
  );
}

interface DiffSourceViewProps {
  label: string;
  source: string;
  otherSource: string;
  side: "a" | "b";
}

const diffMark = Decoration.mark({ class: "cm-anticheat-diff" });

function diffDecorationField(ranges: Token[]): Extension {
  const field = StateField.define<RangeSet<Decoration>>({
    create() {
      const sorted = ranges.slice().sort((a, b) => a.start - b.start);
      const builder = new RangeSetBuilder<Decoration>();
      for (const r of sorted) builder.add(r.start, r.end, diffMark);
      return builder.finish();
    },
    update(value) {
      return value;
    },
    provide: (f) => EditorView.decorations.from(f),
  });
  return field;
}

function DiffSourceView({ label, source, otherSource, side }: DiffSourceViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);

  const diffRanges = useMemo<Token[]>(() => {
    const selfTokens = tokenize(source);
    const otherTokens = tokenize(otherSource);
    const otherSet = new Set(otherTokens.map((t) => t.text));
    return selfTokens.filter((t) => !otherSet.has(t.text));
  }, [source, otherSource]);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: source,
        extensions: [
          pseint(),
          syntaxHighlighting(pseintHighlightStyle),
          EditorView.editable.of(false),
          EditorView.lineWrapping,
          diffDecorationField(diffRanges),
        ],
      }),
      parent: container,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source]);

  return (
    <div className="anticheat-diff-source" data-side={side}>
      <h4>{label}</h4>
      <div ref={containerRef} className="anticheat-diff-cm" />
    </div>
  );
}

interface Token {
  text: string;
  start: number;
  end: number;
}

/** Whitespace-token split (per plan §25 spec). */
function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  const re = /\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    tokens.push({ text: m[0], start: m.index, end: m.index + m[0].length });
  }
  return tokens;
}
