import Link from "next/link";
import { ContactForm } from "./contact-form";

export function LocalSetupRequest({ slug, name, known }: { slug: string; name: string; known: boolean }) {
  return <>
    <section className="section-wrap hero">
      <p className="eyebrow"><Link href="/local">Run locally</Link> / Setup request</p>
      <div className="hero-grid"><div><span className="badge">{known ? "Local install on request" : "Unverified model reference"}</span>
        <h1 className="space-top-sm">Local setup for {name}</h1>
        <p className="lede">This model has no supported one-command recipe in our installer. Tell us about your machine and use case, and we will review whether we can help you set it up.</p>
        <div className="hero-actions"><a className="button button-primary" href="#local-request">Request local setup</a><Link className="button button-secondary" href="/local">Browse supported installs</Link></div>
      </div><aside className="hero-note"><strong>A request, not an installation promise.</strong><span>We first check the model reference, access to weights, model licence and your hardware. We will confirm feasibility and any setup quote before you commit.</span></aside></div>
      {!known && <div className="callout space-top"><strong>We have not verified this model reference.</strong><p>Check the spelling and include the original model link in your message. This page does not confirm that the model or its weights are available.</p></div>}
    </section>
    <section className="section-wrap section"><div className="benefit-grid">
      <article className="benefit"><span className="index">01</span><h2>Share your setup</h2><p>Tell us your operating system, available CPU or GPU, memory and what the model should do.</p></article>
      <article className="benefit"><span className="index">02</span><h2>We check feasibility</h2><p>Model access, licence terms and runtime requirements need review. No hardware or performance figures are assumed here.</p></article>
      <article className="benefit"><span className="index">03</span><h2>Decide after our reply</h2><p>Sending this form is free and creates no order. Buying an installer licence does not add support for this model.</p></article>
    </div></section>
    <section className="section-wrap section" id="local-request"><div className="section-heading"><div><p className="section-kicker">Setup help</p><h2>Request local setup for {name}</h2></div><p>Your model reference stays attached to the request. You receive an email confirmation, then we follow up after review.</p></div>
      <div className="panel"><ContactForm mode="local" models={[{ slug, name }]} selectedModel={slug} /></div>
    </section>
  </>;
}
