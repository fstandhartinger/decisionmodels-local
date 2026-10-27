import fs from "node:fs";
import path from "node:path";
import { catalogRoot } from "./catalog-root";

/** Names only: this map never grants installer support, hardware sizing or licence rights. */
export function localRequestModels(): Record<string, string> {
  const data = JSON.parse(fs.readFileSync(path.join(catalogRoot(), "local-request-models.json"), "utf8")) as { models: Record<string, string> };
  return data.models;
}
