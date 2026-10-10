"use client";

import { FormEvent, useState } from "react";

export function ContactForm({ models, selectedModel }: { models: Array<{ slug: string; name: string }>; selectedModel?: string }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    data.models = new FormData(form).getAll("models").map(String).join(",");
    try {
      const response = await fetch("/local/api/contact", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(data) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Please check the form and try again.");
      form.reset();
      setMessage(result.mail === "queued" ? "Your request is saved. We will follow up by email." : "Your request has been sent. A copy is on its way to your inbox.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The request could not be sent.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="form-grid" onSubmit={submit}>
      <label>Name<input name="name" autoComplete="name" required maxLength={120} /></label>
      <label>Email<input name="email" type="email" autoComplete="email" required maxLength={254} /></label>
      <label>Company <span className="optional">Optional</span><input name="company" autoComplete="organization" maxLength={160} /></label>
      <fieldset className="form-field full-width"><legend>Models</legend><div className="checkbox-list">
        {models.map((model) => <label key={model.slug}><input type="checkbox" name="models" value={model.slug} defaultChecked={model.slug === selectedModel} />{model.name}</label>)}
        {!models.length && <span className="fine-print">Tell us which model you have in mind in the message.</span>}
      </div></fieldset>
      <label>Quantity<input name="quantity" type="number" min="1" max="1000" defaultValue="1" required /></label>
      <label>Where will it run?<select name="location" required defaultValue="office"><option value="office">Office</option><option value="edge">Edge device</option><option value="factory">Factory</option><option value="other">Other</option></select></label>
      <label>Timeline<select name="timeline" required defaultValue="researching"><option value="researching">Researching</option><option value="this-month">This month</option><option value="this-quarter">This quarter</option><option value="later">Later</option></select></label>
      <label className="full-width">Message<textarea name="message" rows={4} maxLength={4000} placeholder="What should the setup handle?" /></label>
      <label className="checkbox-line full-width"><input name="consent" type="checkbox" value="yes" required /><span>I agree that Decision Models can use these details to respond. See the <a className="consent-link" href="https://decisionmodels.io/legal/privacy">privacy notice</a>.</span></label>
      <div className="trap" aria-hidden="true"><label>Leave this field empty<input name="website" tabIndex={-1} autoComplete="off" /></label></div>
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Sending…" : "Request a hardware quote"}</button>
      {message && <p className="form-status" role="status">{message}</p>}
    </form>
  );
}
