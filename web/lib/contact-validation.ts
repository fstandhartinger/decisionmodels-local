const locations = new Set(["office", "edge", "factory", "other"]);
const timelines = new Set(["researching", "this-month", "this-quarter", "later"]);

export type HardwareInquiryInput = {
  name: string;
  email: string;
  company: string | null;
  models: string[];
  hardwareId: string | null;
  quantity: number;
  location: string;
  timeline: string;
  message: string;
};

export const MAX_REQUESTED_MODELS = 20;

export function isRequestedModelSlug(value: unknown): value is string {
  return typeof value === "string" && /^[a-z0-9][a-z0-9.-]{0,80}$/.test(value);
}

export function validateHardwareInquiry(input: Record<string, unknown>, allowedHardwareIds: readonly string[] = []) {
  if (typeof input.website === "string" && input.website.trim()) return { ok: true as const, honeypot: true as const };
  const name = typeof input.name === "string" ? input.name.trim() : "";
  const email = typeof input.email === "string" ? input.email.trim() : "";
  const company = typeof input.company === "string" && input.company.trim() ? input.company.trim() : null;
  const modelsRaw = Array.isArray(input.models) ? input.models : typeof input.models === "string" ? input.models.split(",") : [];
  if (modelsRaw.length > MAX_REQUESTED_MODELS) return { ok: false as const, error: `Choose at most ${MAX_REQUESTED_MODELS} models.` };
  if (modelsRaw.some((value) => typeof value !== "string")) return { ok: false as const, error: "Enter valid model slugs." };
  const models = [...new Set((modelsRaw as string[]).map((value) => value.trim()).filter(Boolean))];
  const hardwareId = typeof input.hardware_id === "string" && input.hardware_id.trim() ? input.hardware_id.trim() : null;
  if (input.hardware_id != null && typeof input.hardware_id !== "string") return { ok: false as const, error: "Choose a valid machine." };
  if (hardwareId && !allowedHardwareIds.includes(hardwareId)) return { ok: false as const, error: "Choose a machine from the list." };
  const quantity = Number(input.quantity);
  const location = typeof input.location === "string" ? input.location : "";
  const timeline = typeof input.timeline === "string" ? input.timeline : "";
  const message = typeof input.message === "string" ? input.message.trim() : "";
  if (name.length < 2 || name.length > 120) return { ok: false as const, error: "Enter a name between 2 and 120 characters." };
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return { ok: false as const, error: "Enter a valid email address." };
  if (company && company.length > 160) return { ok: false as const, error: "Company name must be 160 characters or fewer." };
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 1000) return { ok: false as const, error: "Quantity must be between 1 and 1,000." };
  if (!locations.has(location)) return { ok: false as const, error: "Choose where the hardware will run." };
  if (!timelines.has(timeline)) return { ok: false as const, error: "Choose a timeline." };
  if (message.length > 4000) return { ok: false as const, error: "Message must be 4,000 characters or fewer." };
  if (models.some((slug) => !isRequestedModelSlug(slug))) return { ok: false as const, error: "Enter valid model slugs (up to 81 lowercase letters, digits, dots or hyphens)." };
  if (input.consent !== true && input.consent !== "yes") return { ok: false as const, error: "Consent is required to send this request." };
  return { ok: true as const, honeypot: false as const, value: { name, email, company, models, hardwareId, quantity, location, timeline, message } satisfies HardwareInquiryInput };
}
