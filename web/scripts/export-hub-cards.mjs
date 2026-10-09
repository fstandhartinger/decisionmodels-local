import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { deviceFits, deviceQuotes, suggestDevice } from "../lib/hardware-core.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.resolve(process.argv[2] || path.join(root, "out"));
const catalogDir = process.env.CATALOG_DIR || (fs.existsSync(path.join(root, "catalog")) ? path.join(root, "catalog") : path.join(root, "..", "catalog"));
const modelDirectory = path.join(catalogDir, "models");
const prices = JSON.parse(fs.readFileSync(path.join(catalogDir, "hardware-prices.json"), "utf8"));
const models = fs.existsSync(modelDirectory) ? fs.readdirSync(modelDirectory).filter((name) => name.endsWith(".json")).map((name) => JSON.parse(fs.readFileSync(path.join(modelDirectory, name), "utf8"))).filter((model) => model.hidden !== true) : [];
const devices = prices.devices ?? [];
const shortLabel = (device) => {
  const name = device.name.replace("NVIDIA ", "").replace("Developer Kit", "").trim();
  return `${name}${Number.isFinite(device.memory_gb) ? ` ${device.memory_gb} GB` : ""}`;
};
const sourceList = (device) => (device.prices ?? []).map(({ source, date, value, currency }) => ({ source, date, value, currency }));

fs.mkdirSync(path.join(output, "local-pages"), { recursive: true });
for (const model of models) {
  if (typeof model.slug !== "string" || !/^[a-z0-9](?:[a-z0-9.-]{0,118}[a-z0-9])?$/.test(model.slug)) continue;
  const fitsOn = devices.filter((device) => (model.variants ?? []).some((variant) => deviceFits(model, device, variant))).map(shortLabel);
  const suggestion = suggestDevice(model, devices);
  const card = {
    slug: model.slug,
    min_vram_gb: (model.variants ?? []).map((variant) => variant.min_vram_gb).filter(Number.isFinite).sort((a, b) => a - b)[0] ?? null,
    fits_on: [...new Set(fitsOn)],
    suggested_device: suggestion ? { name: suggestion.name, price_usd: suggestion.price_usd, price_eur: suggestion.price_eur, sources: sourceList(devices.find((device) => device.id === suggestion.id)) } : null,
    licence_note: model.licence?.notes ?? "Model licence not listed in the catalog.",
    page_url: `https://decisionmodels.io/models/${model.slug}/local`,
    installer_policy: model.installer_policy ?? { status: "excluded", reason: "No local installer policy is recorded." }
  };
  fs.writeFileSync(path.join(output, "local-pages", `${model.slug}.json`), `${JSON.stringify(card, null, 2)}\n`);
}

const groups = Object.groupBy ? Object.groupBy(devices, (device) => device.class) : devices.reduce((all, device) => ((all[device.class] ??= []).push(device), all), {});
const hardware = {
  device_classes: Object.entries(groups).map(([deviceClass, members]) => ({
    class: deviceClass,
    devices: members.map((device) => ({ id: device.id, name: device.name, memory_gb: device.memory_gb, memory_kind: device.memory_kind, indicative_price: deviceQuotes(device), sources: sourceList(device) }))
  })),
  page_url: "https://decisionmodels.io/hardware"
};
fs.writeFileSync(path.join(output, "hardware.json"), `${JSON.stringify(hardware, null, 2)}\n`);
process.stdout.write(`exported ${models.length} model card(s) and ${devices.length} hardware device(s) to ${output}\n`);
