import fs from "node:fs";
import path from "node:path";

function hasSharedCatalog(directory: string): boolean {
  return fs.existsSync(path.join(directory, "hardware-prices.json")) && fs.existsSync(path.join(directory, "device-classes.json")) && fs.existsSync(path.join(directory, "models"));
}

export function catalogRoot(workingDirectory = process.cwd(), configuredDirectory = process.env.CATALOG_DIR): string {
  if (configuredDirectory && hasSharedCatalog(configuredDirectory)) return path.resolve(configuredDirectory);

  let current = path.resolve(workingDirectory);
  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = path.join(current, "catalog");
    if (hasSharedCatalog(candidate)) return candidate;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }

  return configuredDirectory ? path.resolve(configuredDirectory) : path.join(path.resolve(workingDirectory), "..", "catalog");
}
