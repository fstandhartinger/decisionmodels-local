const locations = new Set(["office", "edge", "factory", "other"]);
const timelines = new Set(["researching", "this-month", "this-quarter", "later"]);

export type HardwareInquiryInput = {
  name: string;
  email: string;
  company: string | null;
  models: string[];
  quantity: number;
  location: string;
  timeline: string;
  message: string;
};

export function validateHardwareInquiry(input: Record<string, unknown>, allowedModels: Set<string>) {
  if (typeof input.website === "string" && input.website.trim()) return { ok: true as const, honeypot: true as const };
  const name = typeof input.name === "string" ? input.name.trim() : "";
  const email = typeof input.email === "string" ? input.email.trim() : "";
  const company = typeof input.company === "string" && input.company.trim() ? input.company.trim() : null;
  const modelsRaw = Array.isArray(input.models) ? input.models.map(String) : typeof input.models === "string" ? input.models.split(",") : [];
  const models = [...new Set(modelsRaw.map((value) => value.trim()).filter(Boolean))];
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
  if (models.some((slug) => !/^[a-z0-9](?:[a-z0-9.-]{0,118}[a-z0-9])?$/.test(slug) || !allowedModels.has(slug))) return { ok: false as const, error: "Choose models from the catalogue." };
  if (input.consent !== true && input.consent !== "yes") return { ok: false as const, error: "Consent is required to send this request." };
  return { ok: true as const, honeypot: false as const, value: { name, email, company, models, quantity, location, timeline, message } satisfies HardwareInquiryInput };
}
