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

export function deviceStreetPrices(device) {
  const currencies = [...new Set((device.prices ?? []).map((price) => price.currency).filter(Boolean))];
  return Object.fromEntries(currencies.map((currency) => [
    currency,
    median((device.prices ?? []).filter((price) => price.currency === currency).map((price) => price.value))
  ]));
}

export function deviceQuotes(device) {
  return Object.fromEntries(Object.entries(deviceStreetPrices(device)).map(([currency, price]) => [currency, marginQuote(price)]));
}

function isQuantized(variant) {
  const precision = String(variant.precision ?? "").toLowerCase();
  return /q\d|quant|int[48]|fp8|nvfp4/.test(precision);
}

const classPlatforms = {
  "gpu-workstation": ["linux-nvidia", "wsl2-nvidia"],
  gb10: ["linux-nvidia"],
  jetson: ["linux-nvidia"],
  "apple-silicon": ["macos-arm64"],
  "amd-apu": ["linux-cpu"],
  android: ["android"]
};

function requiredMemory(variant, device) {
  const recommended = Number(variant.recommended_vram_gb);
  const minRam = Number(variant.min_ram_gb);
  if (device.memory_kind === "unified" || device.memory_kind === "ram") {
    const requirements = [recommended, minRam].filter((value) => Number.isFinite(value) && value > 0);
    return requirements.length ? Math.max(...requirements) : null;
  }
  return Number.isFinite(recommended) && recommended > 0 ? recommended : null;
}

function compatibleVariant(model, device, variant) {
  const platforms = classPlatforms[device.class] ?? [];
  if (!platforms.some((platform) => (variant.platforms ?? []).includes(platform))) return false;
  const needed = requiredMemory(variant, device);
  if (needed === null || !Number.isFinite(device.memory_gb) || device.memory_gb < needed) return false;
  const isImage = (model.modalities ?? []).includes("image");
  if (isImage && device.supports_image !== true) return false;
  if (["jetson", "android"].includes(device.class)) {
    if ((model.params?.total_b ?? Infinity) > 4 || !isQuantized(variant)) return false;
  }
  return true;
}

export function deviceFits(model, device, variant) {
  if (model.installer_policy?.status === "excluded") return false;
  const variants = variant ? [variant] : (model.variants ?? []);
  return variants.some((candidate) => compatibleVariant(model, device, candidate));
}

export function suggestDevice(model, devices) {
  if (model.installer_policy?.status === "excluded") return null;
  const candidates = devices.flatMap((device) => {
    const variant = [...(model.variants ?? [])]
      .filter((candidate) => compatibleVariant(model, device, candidate))
      .sort((a, b) => requiredMemory(a, device) - requiredMemory(b, device))[0];
    return variant && Object.keys(deviceStreetPrices(device)).length > 0 ? [{ device, variant }] : [];
  });
  const currencyPriority = ["USD", "EUR"].sort((left, right) => {
    const leftCount = candidates.filter(({ device }) => deviceStreetPrices(device)[left] != null).length;
    const rightCount = candidates.filter(({ device }) => deviceStreetPrices(device)[right] != null).length;
    return rightCount - leftCount || left.localeCompare(right);
  });
  const currency = currencyPriority.find((item) => candidates.some(({ device }) => deviceStreetPrices(device)[item] != null));
  candidates.sort(({ device: a }, { device: b }) => {
    const aPrice = currency ? (deviceStreetPrices(a)[currency] ?? Infinity) : Infinity;
    const bPrice = currency ? (deviceStreetPrices(b)[currency] ?? Infinity) : Infinity;
    return aPrice - bPrice || a.name.localeCompare(b.name);
  });
  if (!candidates.length) return null;
  const { device, variant } = candidates[0];
  const quotes = deviceQuotes(device);
  return {
    id: device.id,
    name: device.name,
    class: device.class,
    memory_gb: device.memory_gb,
    memory_kind: device.memory_kind,
    variant_id: variant.id ?? null,
    platforms: variant.platforms ?? [],
    price_usd: quotes.USD ?? null,
    price_eur: quotes.EUR ?? null,
    street_prices: deviceStreetPrices(device),
    source: (device.prices ?? []).map(({ source, date, currency, value }) => ({ source, date, currency, value }))
  };
}
