import fs from "node:fs";
import path from "node:path";
import { catalogRoot } from "./catalog-root";

export type SelfRunModel = {
  name?: string; hf_repo?: string | null; revision?: string | null; params?: string | null; vram_gb?: number | null;
  precision?: string | null; licence?: string | null; gated?: boolean; adapter_base?: string | null;
  runtime?: string; command?: string | null; missing?: string | null;
};
export function selfRunModels(): Record<string, SelfRunModel> {
  const data = JSON.parse(fs.readFileSync(path.join(catalogRoot(), "self-run-models.json"), "utf8"));
  return data.models;
}
export function licenceCopy(licence?: string | null) {
  if (/cc-by-nc|non[ -]?commercial|research (?:use )?only|exaone ai model license/i.test(licence ?? "")) return "Non-commercial: research and personal use only.";
  // Only whole permissive identifiers grant a clear label. Mixed code/weights terms need review.
  if (/^(?:apache[- ]?(?:license[- ]?)?2(?:\.0)?|mit(?: license)?|bsd[- ]?[23][- ]clause)$/i.test((licence ?? "").trim())) return "Commercial use OK under the listed model licence.";
  return "Licence unclear: check the model card before commercial use.";
}

export function selfRunModel(slug: string): SelfRunModel | undefined {
  return selfRunModels()[slug];
}

/** Public Hugging Face repo id (`owner/name`) for display. Internal cache paths map to the repo they hold; anything else is hidden. */
export function publicRepoId(value?: string | null): string | undefined {
  const text = (value ?? "").trim();
  const cached = /^\/workspace\/hf\/hub\/models--([^/]+?)--([^/]+?)(?:\/snapshots\/[^/]+\/?)?$/.exec(text);
  const repo = cached ? `${cached[1]}/${cached[2]}` : text;
  return /^[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._-]*$/.test(repo) && !repo.includes("..") ? repo : undefined;
}

/** Copy-paste request for a locally served vLLM model (OpenAI-compatible chat completion). */
export function localRequestCurl(repo: string) {
  return `curl http://localhost:8000/v1/chat/completions \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({ model: repo, messages: [{ role: "user", content: "Say hello." }], max_tokens: 64 })}'`;
}
