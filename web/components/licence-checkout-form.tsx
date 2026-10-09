"use client";

import { FormEvent, useState } from "react";

export function LicenceCheckoutForm() {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries()) as Record<string, FormDataEntryValue | boolean>;
    data.declaration = new FormData(form).get("declaration") === "yes";
    data.terms = new FormData(form).get("terms") === "yes";
    try {
      const response = await fetch("/local/api/checkout", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(data) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Checkout could not be started.");
      window.location.assign(result.url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Checkout could not be started.");
      setBusy(false);
    }
  }
  return (
    <form className="form-grid" onSubmit={submit}>
      <label className="full-width">Company name<input name="company" autoComplete="organization" required maxLength={160} /></label>
      <label className="full-width">Work email<input name="email" type="email" autoComplete="email" required maxLength={254} /></label>
      <label className="checkbox-line full-width"><input type="checkbox" name="declaration" value="yes" required />My company has more than 10 employees or more than USD 1M in annual revenue.</label>
      <label className="checkbox-line full-width"><input type="checkbox" name="terms" value="yes" required />I agree to the <a href="/local/licence#pricing">commercial licence terms</a>.</label>
      <p className="fine-print full-width">Model licences are separate. Some model weights are not licensed for commercial use.</p>
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Opening checkout…" : "Continue to secure checkout"}</button>
      {error && <p className="form-status error" role="alert">{error}</p>}
    </form>
  );
}
