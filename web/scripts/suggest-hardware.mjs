import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { suggestDevice } from "../lib/hardware-core.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const catalogDir = process.env.CATALOG_DIR || (fs.existsSync(path.join(root, "catalog")) ? path.join(root, "catalog") : path.join(root, "..", "catalog"));
const modelsDirectory = path.join(catalogDir, "models");
const pricesPath = path.join(catalogDir, "hardware-prices.json");
const outputPath = path.join(catalogDir, "hardware-suggestions.json");
const classPath = path.join(catalogDir, "device-classes.json");

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

const prices = readJson(pricesPath);
const classes = readJson(classPath).classes ?? [];
const models = fs.existsSync(modelsDirectory)
  ? fs.readdirSync(modelsDirectory).filter((name) => name.endsWith(".json")).sort().map((name) => readJson(path.join(modelsDirectory, name))).filter((model) => model?.hidden !== true)
  : [];
const suggestions = Object.fromEntries(models.map((model) => [model.slug, suggestDevice(model, prices.devices ?? [], classes)]));
fs.writeFileSync(outputPath, `${JSON.stringify({ generated_utc: new Date().toISOString(), suggestions }, null, 2)}\n`);
process.stdout.write(`wrote ${Object.keys(suggestions).length} hardware suggestions to catalog/hardware-suggestions.json\n`);
