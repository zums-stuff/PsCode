import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";
import {
  listAnticheatPairs,
  updateClassAnticheatThreshold,
} from "../../lib/api";
import type { AnticheatPair } from "../../lib/types";
import AnticheatScopeSelector, {
  type ScopeSelection,
} from "../../components/AnticheatScopeSelector";
import AnticheatThresholdForm from "../../components/AnticheatThresholdForm";
import AnticheatPairList from "../../components/AnticheatPairList";
import AnticheatDiffViewer from "../../components/AnticheatDiffViewer";

/** Engine default threshold (mirrors pseint_judge.similarity.DEFAULT_THRESHOLD). */
const DEFAULT_THRESHOLD = 0.85;

/**
 * /admin/anticheat — report-only anticheat UI (plan todo 25 / §D13).
 *
 * No auto-penalty: nothing here rejects submissions or modifies verdicts.
 * The threshold POSTs to the class-config endpoint; the list endpoint
 * returns pairs ≥ threshold; the diff endpoint returns the ORIGINAL
 * sources verbatim (the D13 normalization internals are NEVER on the
 * wire, plan §39 MUST NOT).
 */
export default function AdminAnticheat() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [selection, setSelection] = useState<ScopeSelection | null>(null);
  const [threshold, setThreshold] = useState<number>(DEFAULT_THRESHOLD);
  const [selectedPair, setSelectedPair] = useState<AnticheatPair | null>(null);

  if (user?.role === "student") {
    return <Navigate to="/403" replace />;
  }

  const pairsQuery = useQuery<AnticheatPair[]>({
    queryKey: [
      "admin",
      "anticheat",
      "pairs",
      selection?.scope,
      selection?.scopeId,
      threshold,
    ],
    queryFn: () =>
      listAnticheatPairs(selection!.scope, selection!.scopeId, threshold),
    enabled: selection !== null,
  });

  function handleScopeApply(next: ScopeSelection) {
    setSelection(next);
    setSelectedPair(null);
    setThreshold(DEFAULT_THRESHOLD);
  }

  async function handleThresholdSubmit(value: number) {
    if (selection === null || selection.scope !== "class") return;
    const updated = await updateClassAnticheatThreshold(selection.scopeId, value);
    setThreshold(updated.anticheat_threshold);
    void queryClient.invalidateQueries({ queryKey: ["admin", "anticheat"] });
  }

  function pairKey(pair: AnticheatPair): string {
    return `${pair.run_a_id}-${pair.run_b_id}`;
  }

  const pairs: AnticheatPair[] = pairsQuery.data ?? [];
  const sameTeamExclusion =
    selection?.scope === "contest" && pairsQuery.isSuccess;

  return (
    <div className="admin-anticheat">
      <div className="admin-page-header">
        <h1>{t("admin.anticheat.title")}</h1>
      </div>

      <p className="hint">{t("admin.anticheat.description")}</p>

      <AnticheatScopeSelector value={selection} onApply={handleScopeApply} />

      {selection !== null && selection.scope === "class" && (
        <AnticheatThresholdForm
          classId={selection.scopeId}
          initialThreshold={threshold}
          defaultThreshold={DEFAULT_THRESHOLD}
          onSubmit={handleThresholdSubmit}
        />
      )}

      {selection !== null && (
        <AnticheatPairList
          pairs={pairs}
          threshold={threshold}
          sameTeamExclusion={sameTeamExclusion}
          loading={pairsQuery.isLoading}
          error={
            pairsQuery.isError ? t("admin.anticheat.pairs.error") : null
          }
          onSelectPair={setSelectedPair}
          selectedPairKey={
            selectedPair === null ? null : pairKey(selectedPair)
          }
        />
      )}

      <AnticheatDiffViewer
        pair={selectedPair}
        onClose={() => setSelectedPair(null)}
      />
    </div>
  );
}
