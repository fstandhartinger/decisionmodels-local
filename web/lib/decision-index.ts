import fs from "node:fs";
import path from "node:path";
import { catalogRoot } from "./catalog-root";

export type DecisionIndexResult = { engine: string; name: string; rank: number; score: number };

export type DecisionIndexSnapshot = {
  version: string;
  generated_utc: string;
  source: string;
  data_source: string;
  models: Record<string, DecisionIndexResult>;
};

export const DECISION_INDEX_NOT_MEASURED = "Decision Index: not yet measured";

export function loadDecisionIndex(file = path.join(catalogRoot(), "decision-index.json")): DecisionIndexSnapshot {
  const parsed = JSON.parse(fs.readFileSync(file, "utf8")) as DecisionIndexSnapshot;
  if (!parsed.version || !parsed.models) throw new Error(`Decision Index snapshot ${file} is incomplete`);
  return parsed;
}

export function decisionIndexDate(snapshot: DecisionIndexSnapshot): string {
  const date = new Date(snapshot.generated_utc);
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(date);
}

/** "#5 on the Decision Index (0.3.1, 10 October 2026)", or an explicit "not yet measured" line. */
export function decisionIndexText(slug: string, snapshot = loadDecisionIndex()): string {
  const result = snapshot.models[slug];
  if (!result || !Number.isFinite(result.rank)) return DECISION_INDEX_NOT_MEASURED;
  return `#${result.rank} on the Decision Index (${snapshot.version}, ${decisionIndexDate(snapshot)})`;
}

export function decisionIndexScoreText(slug: string, snapshot = loadDecisionIndex()): string | null {
  const result = snapshot.models[slug];
  return result && Number.isFinite(result.score) ? `Decision Index score ${result.score.toFixed(2)}` : null;
}
