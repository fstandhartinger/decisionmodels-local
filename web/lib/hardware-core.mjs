export function median(values) {
  const numbers = values.map(Number).filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b);
  if (!numbers.length) return null;
  const middle = Math.floor(numbers.length / 2);
  return numbers.length % 2 ? numbers[middle] : (numbers[middle - 1] + numbers[middle]) / 2;
}

export function marginQuote(streetPrice) {
  const street = Number(streetPrice);
  if (!Number.isFinite(street) || street <= 0) return null;
  const target = Math.max(street * 1.3, street + 150);
  return Math.ceil((target + 1) / 10) * 10 - 1;
}

const defaultClasses = [
  { id: "gpu-workstation", platforms: ["linux-nvidia"], auto_suggest: true },
  { id: "apple-silicon", platforms: ["macos-arm64"], auto_suggest: true },
  { id: "gb10", platforms: ["linux-arm64"], auto_suggest: false },
  { id: "jetson", platforms: ["linux-arm64"], auto_suggest: false },
  { id: "android", platforms: ["android"], auto_suggest: false }
];

function classDefinition(device, classes = defaultClasses) {
  return classes.find((item) => item.id === device.class && item.device_ids?.includes(device.id))
    ?? classes.find((item) => item.id === device.class && !item.device_ids);
}

function deviceStreetPricesForCurrency(device, currency, definition) {
  const listed = median((device.prices ?? []).filter((price) => price.currency === currency).map((price) => price.value));
  if (listed === null) return null;
  const base = Number(definition?.base_system_by_currency?.[currency] ?? 0);
  return listed + (Number.isFinite(base) ? base : 0);
}

export function deviceDisplayName(device, definition) {
  if (definition?.id !== "gpu-workstation") return device.name;
  return `${device.name.replace(/,\s*card(?=\))/i, "")} workstation`;
}

export function deviceStreetPrices(device, definition) {
  const currencies = [...new Set((device.prices ?? []).map((price) => price.currency).filter(Boolean))];
  return Object.fromEntries(currencies.map((currency) => [currency, deviceStreetPricesForCurrency(device, currency, definition)]));
}

export function deviceQuotes(device, definition) {
  return Object.fromEntries(Object.entries(deviceStreetPrices(device, definition)).map(([currency, price]) => [currency, marginQuote(price)]));
}

function isQuantized(variant) {
  const precision = String(variant.precision ?? "").toLowerCase();
  return /q\d|quant|int[48]|fp8|nvfp4/.test(precision);
}

function requiredMemory(variant, definition) {
  if (definition.id === "apple-silicon") {
    const ram = Number(variant.min_ram_gb);
    return Number.isFinite(ram) && ram > 0 ? ram : null;
  }
  const recommended = Number(variant.recommended_vram_gb);
  return Number.isFinite(recommended) && recommended > 0 ? recommended : null;
}

export function hasExecutableInstallRecipe(variant) {
  const processes = variant.install?.processes;
  return Array.isArray(processes) && processes.length > 0 && processes.every((process) =>
    Array.isArray(process.command) && process.command.length > 0
      && process.command.every((argument) => typeof argument === "string" && argument.trim().length > 0)
  );
}

function compatibleVariant(model, device, variant, definition) {
  if (!hasExecutableInstallRecipe(variant)) return false;
  if (!definition?.auto_suggest || (definition.device_ids && !definition.device_ids.includes(device.id))) return false;
  if (!(definition.platforms ?? []).some((platform) => (variant.platforms ?? []).includes(platform))) return false;
  const needed = requiredMemory(variant, definition);
  if (needed === null || !Number.isFinite(device.memory_gb) || device.memory_gb < needed) return false;
  if (["jetson", "android"].includes(definition.id)) {
    if ((model.params?.total_b ?? Infinity) > 4 || !isQuantized(variant)) return false;
  }
  return true;
}

export function deviceFits(model, device, variant, classes = defaultClasses) {
  if (model.installer_policy?.status === "excluded") return false;
  const definition = classDefinition(device, classes);
  if (!definition?.auto_suggest) return false;
  const variants = variant ? [variant] : (model.variants ?? []);
  return variants.some((candidate) => compatibleVariant(model, device, candidate, definition));
}

export function suggestDevice(model, devices, classes = defaultClasses) {
  if (model.installer_policy?.status === "excluded") return null;
  const candidates = devices.flatMap((device) => {
    const definition = classDefinition(device, classes);
    if (!definition?.auto_suggest) return [];
    const variant = [...(model.variants ?? [])]
      .filter((candidate) => compatibleVariant(model, device, candidate, definition))
      .sort((a, b) => requiredMemory(a, definition) - requiredMemory(b, definition))[0];
    return variant && Object.keys(deviceStreetPrices(device, definition)).length > 0 ? [{ device, variant, definition }] : [];
  });
  if (!candidates.length) return null;

  const currencyPriority = ["USD", "EUR"].sort((left, right) => {
    const leftCount = candidates.filter(({ device, definition }) => deviceStreetPrices(device, definition)[left] != null).length;
    const rightCount = candidates.filter(({ device, definition }) => deviceStreetPrices(device, definition)[right] != null).length;
    return rightCount - leftCount || left.localeCompare(right);
  });
  const currency = currencyPriority.find((item) => candidates.some(({ device, definition }) => deviceStreetPrices(device, definition)[item] != null));
  candidates.sort(({ device: a, definition: aDefinition }, { device: b, definition: bDefinition }) => {
    const aPrice = currency ? (deviceStreetPrices(a, aDefinition)[currency] ?? Infinity) : Infinity;
    const bPrice = currency ? (deviceStreetPrices(b, bDefinition)[currency] ?? Infinity) : Infinity;
    return aPrice - bPrice || a.name.localeCompare(b.name);
  });

  const { device, variant, definition } = candidates[0];
  const quotes = deviceQuotes(device, definition);
  return {
    id: device.id,
    name: deviceDisplayName(device, definition),
    class: device.class,
    memory_gb: device.memory_gb,
    memory_kind: device.memory_kind,
    variant_id: variant.id ?? null,
    install_status: variant.install?.verified?.status === "verified" ? "tested" : "ready_unverified",
    platforms: variant.platforms ?? [],
    price_usd: quotes.USD ?? null,
    price_eur: quotes.EUR ?? null,
    street_prices: deviceStreetPrices(device, definition),
    source: (device.prices ?? []).map(({ source, date, currency, value }) => ({ source, date, currency, value }))
  };
}
