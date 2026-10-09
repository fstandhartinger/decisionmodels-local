import { describe, expect, it } from "vitest";
import { deviceFits, deviceQuotes, deviceStreetPrices, marginQuote, median, suggestDevice } from "../lib/hardware-core.mjs";
import { loadCatalog } from "../lib/catalog";
import { classRunsToday, cloudOptionsFor, loadDeviceClasses, loadHardwarePrices, loadSuggestions } from "../lib/hardware-data";
import { catalogRoot } from "../lib/catalog-root";

describe("hardware prices", () => {
  it("loads the real shared catalogue with device classes, model suggestions, and cloud prices", () => {
    const prices = loadHardwarePrices();
    const classes = loadDeviceClasses();
    const suggestions = loadSuggestions();

    expect(catalogRoot()).toContain("catalog");
    expect(loadCatalog().length).toBeGreaterThan(0);
    expect(prices.devices?.length).toBeGreaterThan(0);
    expect(classes.length).toBeGreaterThan(0);
    expect(classes.every((item) => item.device_ids.every((id) => prices.devices?.some((device) => device.id === id)))).toBe(true);
    expect(classes.every((item) => classRunsToday(loadCatalog(), prices.devices ?? [], item).startsWith("Runs today:"))).toBe(true);
    expect(Object.values(suggestions).some(Boolean)).toBe(true);
    expect(prices.cloud?.length).toBeGreaterThan(0);
  });

  it("uses a currency-specific median and the margin floor", () => {
    expect(median([100, 140, 120])).toBe(120);
    expect(deviceStreetPrices({ id: "x", name: "X", class: "gpu-workstation", memory_gb: 24, prices: [
      { value: 1000, currency: "USD", source: "a", date: "2026-10-09" },
      { value: 1200, currency: "USD", source: "b", date: "2026-10-09" },
      { value: 900, currency: "EUR", source: "c", date: "2026-10-09" }
    ] })).toEqual({ USD: 1100, EUR: 900 });
    expect(marginQuote(1000)).toBe(1309);
    expect(marginQuote(100)).toBe(259);
    expect(marginQuote(0)).toBeNull();
    expect(deviceQuotes({ id: "x", name: "X", class: "gpu-workstation", memory_gb: 24, prices: [{ value: 1000, currency: "USD", source: "a", date: "2026-10-09" }] })).toEqual({ USD: 1309 });
  });

  it("adds the complete base system before applying the existing quote margin", () => {
    const card = { id: "5090", name: "RTX 5090", class: "gpu-workstation", memory_gb: 32, memory_kind: "vram", prices: [{ value: 2000, currency: "USD", source: "a", date: "2026-10-09" }] };
    const definition = { id: "gpu-workstation", title: "GPU workstation", platforms: ["linux-nvidia"], device_ids: ["5090"], auto_suggest: true, base_system_by_currency: { USD: 1500, EUR: 1400 } };
    expect(deviceStreetPrices(card, definition)).toEqual({ USD: 3500 });
    expect(deviceQuotes(card, definition)).toEqual({ USD: 4559 });
  });

  it("picks a device that fits the recommended memory and image needs", () => {
    const model = { params: { total_b: 3 }, modalities: ["text", "image"], installer_policy: { status: "supported" }, variants: [{ precision: "q4_k_m", min_vram_gb: 8, recommended_vram_gb: 12, platforms: ["linux-nvidia"] }] };
    const devices = [
      { id: "jetson", name: "Jetson", class: "jetson", memory_gb: 16, memory_kind: "unified", prices: [{ value: 500, currency: "USD", source: "a", date: "2026-10-09" }] },
      { id: "gpu", name: "GPU", class: "gpu-workstation", memory_gb: 16, memory_kind: "vram", supports_image: true, prices: [{ value: 900, currency: "USD", source: "b", date: "2026-10-09" }] },
      { id: "large", name: "Large GPU", class: "gpu-workstation", memory_gb: 24, memory_kind: "vram", supports_image: true, prices: [{ value: 1200, currency: "USD", source: "c", date: "2026-10-09" }] }
    ];
    expect(suggestDevice(model, devices)?.id).toBe("gpu");
    expect(suggestDevice({ ...model, installer_policy: { status: "excluded" } }, devices)).toBeNull();
    expect(suggestDevice({ ...model, variants: [{ precision: "bf16", min_vram_gb: 8, recommended_vram_gb: 12, platforms: ["linux-nvidia"] }] }, devices)?.id).toBe("gpu");
  });

  it("matches device class to the supported platform and uses host RAM when a unified-memory variant has no VRAM figure", () => {
    const model = { params: { total_b: 12 }, modalities: ["text"], installer_policy: { status: "supported" }, variants: [
      { id: "gpu-bf16", precision: "bf16", recommended_vram_gb: 96, min_ram_gb: 32, platforms: ["linux-nvidia"] },
      { id: "mps-fp16", precision: "fp16", recommended_vram_gb: 0, min_ram_gb: 48, platforms: ["macos-arm64"] }
    ] };
    const devices = [
      { id: "small-mac", name: "Small Mac", class: "apple-silicon", memory_gb: 16, memory_kind: "unified", prices: [{ value: 1000, currency: "USD", source: "a", date: "2026-10-09" }] },
      { id: "large-mac", name: "Large Mac", class: "apple-silicon", memory_gb: 64, memory_kind: "unified", prices: [{ value: 2000, currency: "USD", source: "b", date: "2026-10-09" }] },
      { id: "gpu", name: "GPU", class: "gpu-workstation", memory_gb: 96, memory_kind: "vram", prices: [{ value: 3000, currency: "USD", source: "c", date: "2026-10-09" }] }
    ];
    expect(suggestDevice(model, devices)).toMatchObject({ id: "large-mac", variant_id: "mps-fp16", memory_gb: 64 });
  });

  it("does not auto-suggest edge devices even for small quantised variants", () => {
    const model = { params: { total_b: 4 }, modalities: ["text"], installer_policy: { status: "supported" }, variants: [{ precision: "q4_k_m", recommended_vram_gb: 8, platforms: ["linux-nvidia"] }] };
    const device = { id: "jetson", name: "Jetson", class: "jetson", memory_gb: 8, memory_kind: "unified", prices: [{ value: 500, currency: "USD", source: "a", date: "2026-10-09" }] };
    expect(suggestDevice(model, [device])).toBeNull();
    expect(suggestDevice({ ...model, params: { total_b: 5 } }, [device])).toBeNull();
    expect(suggestDevice({ ...model, variants: [{ precision: "bf16", recommended_vram_gb: 8, platforms: ["linux-nvidia"] }] }, [device])).toBeNull();
    expect(deviceFits(model, device, model.variants[0])).toBe(false);
  });

  it("uses the class platform and auto-suggest policy for both suggestions and fits_on", () => {
    const model = { installer_policy: { status: "supported" }, variants: [{ id: "cuda", recommended_vram_gb: 32, platforms: ["linux-nvidia"] }] };
    const devices = [
      { id: "gpu", name: "GPU card", class: "gpu-workstation", memory_gb: 32, prices: [{ value: 1000, currency: "USD", source: "a", date: "2026-10-09" }] },
      { id: "spark", name: "Spark", class: "gb10", memory_gb: 128, prices: [{ value: 500, currency: "USD", source: "b", date: "2026-10-09" }] }
    ];
    const classes = [
      { id: "gpu-workstation", title: "GPU workstation", platforms: ["linux-nvidia"], device_ids: ["gpu"], auto_suggest: true, base_system_by_currency: { USD: 1500 } },
      { id: "gb10", title: "GB10", platforms: ["linux-arm64"], device_ids: ["spark"], auto_suggest: false }
    ];
    expect(suggestDevice(model, devices, classes)).toMatchObject({ id: "gpu", price_usd: 3259 });
    expect(deviceFits(model, devices[0], model.variants[0], classes)).toBe(true);
    expect(deviceFits(model, devices[1], model.variants[0], classes)).toBe(false);
  });

  it("shows only cloud instances whose recorded VRAM meets the smallest supported GPU requirement", () => {
    const model = { installer_policy: { status: "supported" }, variants: [
      { recommended_vram_gb: 48, platforms: ["linux-nvidia"] },
      { recommended_vram_gb: 32, platforms: ["macos-arm64"] }
    ] };
    const prices = { cloud: [
      { provider: "runpod", instance: "small", vram_gb: 24, usd_per_hour: 0.1, source: "https://example.com/small" },
      { provider: "runpod", instance: "fit", vram_gb: 48, usd_per_hour: 1.2, source: "https://example.com/fit" },
      { provider: "aws", instance: "large", vram_gb: 80, usd_per_hour: 2.1, source: "https://example.com/large" },
      { provider: "azure", instance: "unknown-vram", vram_gb: null, usd_per_hour: 0.2, source: "https://example.com/unknown" }
    ] };
    expect(cloudOptionsFor(model, prices).map((row) => row.instance)).toEqual(["fit", "large"]);
  });
});
