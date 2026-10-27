"use client";

import { FormEvent, useState } from "react";
import { isRequestedModelSlug } from "@/lib/contact-validation";

export function ContactForm({ models, selectedModel, hardware = [], selectedHardware, mode = "hardware" }: { models: Array<{ slug: string; name: string }>; selectedModel?: string; hardware?: Array<{ id: string; name: string }>; selectedHardware?: string; mode?: "hardware" | "local" }) {
  const requestedModel = isRequestedModelSlug(selectedModel) && !models.some((model) => model.slug === selectedModel) ? selectedModel : undefined;
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
      const machine = hardware.find((device) => device.id === data.hardware_id)?.name;
      const interest = mode === "local" ? `Your local setup request for ${models.find((model) => model.slug === selectedModel)?.name ?? selectedModel}` : machine ? `Your pilot interest in ${machine}` : "Your pilot interest";
      form.reset();
      setMessage(result.mail === "queued" ? `${interest} is saved. We will follow up by email.` : `${interest} has been sent. A copy is on its way to your inbox.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The request could not be sent.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="form-grid" onSubmit={submit}>
      <input type="hidden" name="request_kind" value={mode} />
      <label>Name<input name="name" autoComplete="name" required maxLength={120} /></label>
      <label>Email<input name="email" type="email" autoComplete="email" required maxLength={254} /></label>
      <label>Company <span className="optional">Optional</span><input name="company" autoComplete="organization" maxLength={160} /></label>
      {mode === "local" ? <div className="form-field full-width"><strong>Model: {models.find((model) => model.slug === selectedModel)?.name ?? selectedModel}</strong><input type="hidden" name="models" value={selectedModel} /></div> : <>
      <fieldset className="form-field full-width"><legend>Models</legend><div className="checkbox-list">
        {models.map((model) => <label key={model.slug}><input type="checkbox" name="models" value={model.slug} defaultChecked={model.slug === selectedModel} />{model.name}</label>)}
        {requestedModel && <label><input type="checkbox" name="models" value={requestedModel} defaultChecked />Requested model: {requestedModel}</label>}
        {!models.length && !requestedModel && <span className="fine-print">Tell us which model you have in mind in the message.</span>}
      </div></fieldset>
      <label className="full-width">Machine of interest<select name="hardware_id" defaultValue={selectedHardware ?? ""}><option value="">Help me choose a machine</option>{hardware.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}</select></label>
      <label>Quantity<input name="quantity" type="number" min="1" max="1000" defaultValue="1" required /></label>
      <label>Where will it run?<select name="location" required defaultValue="office"><option value="office">Office</option><option value="edge">Edge device</option><option value="factory">Factory</option><option value="other">Other</option></select></label>
      </>}
      <label>Timeline<select name="timeline" required defaultValue="researching"><option value="researching">Researching</option><option value="this-month">This month</option><option value="this-quarter">This quarter</option><option value="later">Later</option></select></label>
      <label className="full-width">Message<textarea name="message" rows={4} maxLength={4000} placeholder={mode === "local" ? "Operating system, CPU/GPU, memory, original model link and what you need help with" : "What should the setup handle?"} /></label>
      <label className="checkbox-line full-width"><input name="consent" type="checkbox" value="yes" required /><span>I agree that Decision Models can use these details to respond. See the <a className="consent-link" href="https://decisionmodels.io/legal/privacy">privacy notice</a>.</span></label>
      <div className="trap" aria-hidden="true"><label>Leave this field empty<input name="website" tabIndex={-1} autoComplete="off" /></label></div>
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Sending…" : mode === "local" ? "Request local setup" : "Register pilot interest"}</button>
      {message && <p className="form-status" role="status">{message}</p>}
    </form>
  );
}
