import fs from "node:fs";
import path from "node:path";

export function catalogRoot(): string {
  if (process.env.CATALOG_DIR) return process.env.CATALOG_DIR;
  const local = path.join(process.cwd(), "catalog");
  return fs.existsSync(local) ? local : path.join(process.cwd(), "..", "catalog");
}
