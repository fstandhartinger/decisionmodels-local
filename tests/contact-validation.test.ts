import { describe, expect, it } from "vitest";
import { validateHardwareInquiry } from "../lib/contact-validation";

const allowed = new Set(["qwen3-4b-instruct-2507"]);
const valid = { name: "Taylor Smith", email: "taylor@example.com", company: "Example Ltd", models: "qwen3-4b-instruct-2507", quantity: "2", location: "office", timeline: "this-quarter", message: "Two local systems", consent: "yes" };

describe("hardware inquiry validation", () => {
  it("accepts a valid inquiry and normalizes its values", () => {
    const result = validateHardwareInquiry(valid, allowed);
    expect(result.ok && !result.honeypot && result.value).toMatchObject({ email: "taylor@example.com", quantity: 2, models: ["qwen3-4b-instruct-2507"] });
  });
  it("accepts catalog model slugs containing version dots", () => {
    const result = validateHardwareInquiry({ ...valid, models: ["bobcat-flash-1.2"] }, new Set(["bobcat-flash-1.2"]));
    expect(result.ok && !result.honeypot && result.value?.models).toEqual(["bobcat-flash-1.2"]);
  });
  it("rejects invalid model names and missing consent", () => {
    expect(validateHardwareInquiry({ ...valid, models: "unknown-model" }, allowed)).toMatchObject({ ok: false });
    expect(validateHardwareInquiry({ ...valid, consent: false }, allowed)).toMatchObject({ ok: false });
  });
  it("silently accepts the honeypot without recording a request", () => {
    expect(validateHardwareInquiry({ website: "bot-filled" }, allowed)).toEqual({ ok: true, honeypot: true });
  });
});
