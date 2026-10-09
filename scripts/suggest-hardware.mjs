import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { suggestDevice } from "../lib/hardware-core.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const modelsDirectory = path.join(root, "catalog", "models");
const pricesPath = path.join(root, "catalog", "hardware-prices.json");
const outputPath = path.join(root, "catalog", "hardware-suggestions.json");

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

const prices = readJson(pricesPath);
const models = fs.existsSync(modelsDirectory)
  ? fs.readdirSync(modelsDirectory).filter((name) => name.endsWith(".json")).sort().map((name) => readJson(path.join(modelsDirectory, name)))
  : [];
const suggestions = Object.fromEntries(models.map((model) => [model.slug, suggestDevice(model, prices.devices ?? [])]));
fs.writeFileSync(outputPath, `${JSON.stringify({ generated_utc: new Date().toISOString(), suggestions }, null, 2)}\n`);
process.stdout.write(`wrote ${Object.keys(suggestions).length} hardware suggestions to catalog/hardware-suggestions.json\n`);
