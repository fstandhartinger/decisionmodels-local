import { describe, expect, it } from "vitest";
import { validateHardwareInquiry } from "../lib/contact-validation";

const valid = { name: "Taylor Smith", email: "taylor@example.com", company: "Example Ltd", models: "qwen3-4b-instruct-2507", quantity: "2", location: "office", timeline: "this-quarter", message: "Two local systems", consent: "yes" };

describe("hardware inquiry validation", () => {
  it("accepts a valid inquiry and normalizes its values", () => {
    const result = validateHardwareInquiry(valid);
    expect(result.ok && !result.honeypot && result.value).toMatchObject({ email: "taylor@example.com", quantity: 2, models: ["qwen3-4b-instruct-2507"] });
  });
  it("accepts catalog model slugs containing version dots", () => {
    const result = validateHardwareInquiry({ ...valid, models: ["bobcat-flash-1.2"] });
    expect(result.ok && !result.honeypot && result.value?.models).toEqual(["bobcat-flash-1.2"]);
  });
  it("rejects invalid model names and missing consent", () => {
    expect(validateHardwareInquiry({ ...valid, models: "../unknown-model" })).toMatchObject({ ok: false });
    expect(validateHardwareInquiry({ ...valid, consent: false })).toMatchObject({ ok: false });
  });
  it("accepts unknown slugs and keeps them alongside catalog models", () => {
    const models = ["qwen3-4b-instruct-2507", "pplx-decider-v1-1-27b", "jpt-9b", "vllm-sr-d3", "h2o-lightning-31b"];
    expect(validateHardwareInquiry({ ...valid, models })).toMatchObject({ ok: true, value: { models } });
  });
  it("enforces slug shape, length, type and count", () => {
    for (const models of [["Uppercase"], ["a/b"], ["<script>"], ["a".repeat(82)], [42], Array.from({ length: 21 }, (_, i) => `model-${i}`)]) {
      expect(validateHardwareInquiry({ ...valid, models })).toMatchObject({ ok: false });
    }
    expect(validateHardwareInquiry({ ...valid, models: ["a".repeat(81)] })).toMatchObject({ ok: true });
    expect(validateHardwareInquiry({ ...valid, models: Array.from({ length: 20 }, (_, i) => `model-${i}`) })).toMatchObject({ ok: true });
  });
  it("keeps a known hardware choice and rejects unknown or non-string choices", () => {
    const allowed = ["jetson-orin-nano-super"];
    expect(validateHardwareInquiry({ ...valid, hardware_id: allowed[0] }, allowed)).toMatchObject({ ok: true, value: { hardwareId: allowed[0], models: ["qwen3-4b-instruct-2507"] } });
    for (const hardware_id of ["not-in-the-device-list", "../escape", [allowed[0]], 42]) {
      expect(validateHardwareInquiry({ ...valid, hardware_id }, allowed)).toMatchObject({ ok: false });
    }
    expect(validateHardwareInquiry({ ...valid, hardware_id: "" }, allowed)).toMatchObject({ ok: true, value: { hardwareId: null } });
  });
  it("allowlists local/hardware kinds and keeps a local request to one selected model", () => {
    expect(validateHardwareInquiry({ ...valid, request_kind: "local", models: ["h2o-lightning-31b"] })).toMatchObject({ ok: true, value: { requestKind: "local", models: ["h2o-lightning-31b"], hardwareId: null, location: "other", quantity: 1 } });
    expect(validateHardwareInquiry(valid)).toMatchObject({ ok: true, value: { requestKind: "hardware" } });
    for (const request_kind of ["api", "LOCAL", null, 42]) expect(validateHardwareInquiry({ ...valid, request_kind })).toMatchObject({ ok: false });
    expect(validateHardwareInquiry({ ...valid, request_kind: "local", models: [] })).toMatchObject({ ok: false });
    expect(validateHardwareInquiry({ ...valid, request_kind: "local", hardware_id: "jetson-orin-nano-super" }, ["jetson-orin-nano-super"])).toMatchObject({ ok: false });
  });
  it("silently accepts the honeypot without recording a request", () => {
    expect(validateHardwareInquiry({ website: "bot-filled" })).toEqual({ ok: true, honeypot: true });
  });
});
