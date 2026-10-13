import type { Metadata } from "next";
import Link from "next/link";
import { ContactForm } from "@/components/contact-form";
import { loadCatalog } from "@/lib/catalog";
import { cloudRequirement, dateText, hourlyMoney, loadHardwarePrices, publicCloudGpuName, publicCloudInstanceName, publicCloudProviderName, sourceUrl, cheapestCloudOptionFor } from "@/lib/hardware-data";
import { MODEL_COLUMNS, OFFER_LABEL, SOURCES, TIERS, type Fit, type TierDevice } from "@/lib/hardware-tiers";

export const metadata: Metadata = { title: "Run decision models on your own hardware", description: "Device tiers from edge boards to rack servers: which decision models fit, measured and estimated speed, power, noise and price, and what we can pre-install for you.", alternates: { canonical: "/hardware" } };

type HardwareProps = { searchParams: Promise<{ model?: string }> };

const fitBadge: Record<Fit["level"], { label: string; className: string }> = {
  measured: { label: "Measured", className: "badge signal" },
  estimate: { label: "Estimate", className: "badge" },
  fits: { label: "Fits", className: "badge" },
  no: { label: "No", className: "badge warn" }
};

function FitCell({ fit }: { fit: Fit }) {
  const badge = fitBadge[fit.level];
  return <td><span className={badge.className}>{badge.label}</span><div className="source-note">{fit.text}</div></td>;
}

function SourceLinks({ ids }: { ids: string[] }) {
  return <ul className="price-source-list">{ids.map((id) => {
    const source = SOURCES[id];
    if (!source) return null;
    return <li key={id}>{source.url ? <a href={source.url}>{source.label}</a> : <span>{source.label}</span>} · {source.date}</li>;
  })}</ul>;
}

function DeviceCard({ device }: { device: TierDevice }) {
  return <article className={`price-card ${device.offer === "preinstall" ? "featured" : ""}`} id={device.id}>
    <span className={device.offer === "preinstall" ? "badge signal" : device.offer === "not-yet" ? "badge warn" : "badge"}>{OFFER_LABEL[device.offer]}</span>
    <h3 className="space-top-sm">{device.name}</h3>
    {device.examples && <p className="fine-print">{device.examples}</p>}
    <dl className="hw-facts space-top-sm">
      <div><dt>Memory</dt><dd>{device.memory}</dd></div>
      <div><dt>Price</dt><dd>{device.price}</dd></div>
      <div><dt>Power</dt><dd>{device.power}</dd></div>
      <div><dt>Noise</dt><dd>{device.noise}</dd></div>
    </dl>
    <p className="variant-note">{device.offerNote}</p>
    <details className="price-source-disclosure"><summary>Sources ({device.sources.length})</summary><SourceLinks ids={device.sources} /></details>
  </article>;
}

export default async function HardwarePage({ searchParams }: HardwareProps) {
  const { model: selectedSlug } = await searchParams;
  const models = loadCatalog();
  const selectedModel = selectedSlug ? models.find((item) => item.slug === selectedSlug) : undefined;
  const prices = loadHardwarePrices();
  const cloudModels = models.map((model) => ({ model, requirement: cloudRequirement(model), offer: cheapestCloudOptionFor(model, prices) })).filter((item) => item.requirement !== null);
  const allDevices = TIERS.flatMap((tier) => tier.devices.map((device) => ({ tier, device })));

  return <>
    <section className="section-wrap hero">
      <div className="hero-grid"><div><p className="eyebrow">Pre-installed hardware</p><h1>Run decision models on your own hardware.</h1><p className="lede">From a small edge board to a rack of GPUs: see which models fit, how many decisions per second to expect, and what each machine costs. On request we deliver an NVIDIA workstation set up for you, or you use your own device with our installer.</p><div className="hero-actions"><a className="button button-primary" href="#tiers">Compare devices</a><a className="button button-secondary" href="#request">Ask for a setup</a></div></div>
        <aside className="hero-note"><strong>Speeds marked “measured” come from our own runs.</strong><span>Everything else is labelled as an estimate. A decision is one question answered with a probability for each option.</span></aside></div>
    </section>

    <section className="section-wrap section">
      <div className="section-heading"><div><p className="section-kicker">Why self-host decisions</p><h2>Decisions are a good fit for your own hardware</h2></div></div>
      <div className="benefit-grid">
        {[["Sensitive", "Decisions are made on customer records, contracts, transactions and internal policies. On your own machine, that data never leaves your network."], ["Latency-critical", "A decision often sits inside a user request or a control loop. A local model answers without a round trip to a hosted API."], ["High-volume", "Classification, routing and review run on every item, all day. A machine you own has a fixed cost however many decisions it makes."], ["Offline capable", "After the model files are downloaded, the machine can serve decisions without any internet connection."]].map(([title, copy], index) => <article className="benefit" key={title}><span className="index">0{index + 1}</span><h2>{title}</h2><p>{copy}</p></article>)}
      </div>
    </section>

    <section className="section-wrap section">
      <div className="panel-grid">
        <div className="panel"><p className="section-kicker">Why it runs fast</p><h2>The REAX Engine</h2><p className="space-top-sm">Decision models read a prompt and score a few answer options. They do not write long text. The REAX Engine is our serving engine built for exactly that: it reads the prompt once, scores the options and skips token-by-token generation.</p><p>On one NVIDIA RTX PRO 6000, Perplexity Decider v1.1 went from 5.0 decisions per second on the author’s reference server to 15.7 on the REAX Engine (FP8), with the same benchmark scores within noise.</p><p className="fine-print">The REAX Engine runs on NVIDIA GPUs (CUDA). On Apple Silicon and other platforms we plan to use standard open-source runtimes (not tested yet).</p></div>
        <div className="panel"><p className="section-kicker">Models in this guide</p><h2>What we size for</h2><ul className="plain-steps space-top-sm">{MODEL_COLUMNS.map((column) => <li key={column.key}><strong>{column.title}</strong> · <span className="fine-print">{column.detail}</span></li>)}</ul><p className="fine-print">Memory figures assume the precision shown in the table. Lower precision uses less memory but must pass our quality checks before we use it. Blink v0.3 for local installs is offered subject to its licence.</p></div>
      </div>
    </section>

    {selectedModel && <section className="section-wrap"><div className="callout"><strong>Selected model: {selectedModel.name}</strong><p>Check the memory it needs on the model page, then pick a device below with at least that much memory.</p><Link href={`/models/${selectedModel.slug}/local`}>View model requirements →</Link></div></section>}

    <section className="section-wrap section" id="tiers">
      <div className="section-heading"><div><p className="section-kicker">Device tiers</p><h2>Edge, desk, workstation, rack</h2></div><p>Prices are device street or list prices in Germany (incl. VAT) and the US, with the date we checked them. Setup, shipping and support are quoted separately on request.</p></div>
      {TIERS.map((tier) => <div className="section hardware-class" key={tier.id} id={`tier-${tier.id}`}>
        <div className="section-heading"><div><p className="section-kicker">{tier.kicker}</p><h3>{tier.title}</h3></div><p>{tier.summary}</p></div>
        <div className="model-grid">{tier.devices.map((device) => <DeviceCard key={device.id} device={device} />)}</div>
      </div>)}
    </section>

    <section className="section-wrap section" id="fit">
      <div className="section-heading"><div><p className="section-kicker">Model fit and speed</p><h2>Which model fits where, and how fast</h2></div><p>Decisions per second (dec/s) on Decision Index traffic, several questions per request, at the best tested concurrency. Short single-question prompts run faster; long documents run slower.</p></div>
      <div className="table-wrap"><table><thead><tr><th>Device</th>{MODEL_COLUMNS.map((column) => <th key={column.key}>{column.title}</th>)}</tr></thead><tbody>
        {allDevices.map(({ tier, device }) => <tr key={device.id}><td><strong>{device.name}</strong><div className="source-note">{tier.title} · {device.memory}</div></td><FitCell fit={device.fits.s1pro} /><FitCell fit={device.fits.moe} /><FitCell fit={device.fits.quyet} /><FitCell fit={device.fits.small} /></tr>)}
      </tbody></table></div>
      <p className="mobile-scroll-hint">Swipe horizontally to see all models.</p>
      <details className="disclosure"><summary>How we measure and estimate</summary>
        <p><strong>Measured</strong> figures are our own runs on rented NVIDIA RTX PRO 6000 (96 GB) and RTX 5090 (32 GB) cards in October 2026. The RTX 5090 figure for s1-pro-class models is offline packed throughput from our hardware sweep.</p>
        <p><strong>Estimates</strong> scale our RTX PRO 6000 measurements by the ratio of published prompt-processing benchmarks between that card and the target device (LMSYS, JetsonHacks). They can be off by about half in either direction. We have not yet run our models on Apple Silicon, AMD, Jetson or GB10 hardware, so those devices show estimates or only a memory fit; we benchmark your configuration before delivery.</p>
        <p><strong>Fits</strong> means the model weights at that precision fit in the device memory with room for context; we do not give a speed where no comparable benchmark exists.</p>
      </details>
    </section>

    <section className="section-wrap section" id="offer">
      <div className="section-heading"><div><p className="section-kicker">How we can deliver</p><h2>Pre-installed, or bring your own</h2></div></div>
      <div className="split">
        <div className="panel"><span className="badge signal">Pre-installed by us, on request</span><h3 className="space-top-sm">A ready machine</h3><p>We buy a new workstation through regular retail or distribution channels in the EU, install the runtime, the model and a Jev-compatible endpoint, run a burn-in test and ship it to you.</p><ul className="plain-steps"><li>Workstations with RTX PRO 6000 or RTX 5090, today</li><li>GB10 systems (ASUS, Gigabyte, Dell, Lenovo, HP), once our Arm builds pass testing</li><li>Mac mini and Mac Studio, once our Apple Silicon builds pass testing; macOS stays untouched and our software is added as separate apps</li></ul></div>
        <div className="panel"><span className="badge">Bring your own device</span><h3 className="space-top-sm">Your machine, our installer</h3><p>Use hardware you already own or buy directly from the maker. Our <Link href="/local">installer and setup guide</Link> detects the device, downloads pinned model files and starts a local endpoint. We can also install remotely over SSH.</p><ul className="plain-steps"><li>NVIDIA Jetson boards and GB10 systems</li><li>tiny corp tinybox (sold directly by tiny corp)</li><li>Any Linux machine with a recent NVIDIA GPU</li></ul></div>
      </div>
      <p className="source-note space-top-sm">We are an independent integrator. We are not an authorised reseller or partner of Apple, NVIDIA, AMD, tiny corp or any system maker, and product names are used only to identify the hardware. The manufacturer’s warranty follows the manufacturer’s own terms; as the seller we provide the statutory warranty. Quotes are confirmed by email.</p>
    </section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Cloud and remote GPUs</p><h2>Use a GPU you already rent</h2></div><p>For each model, this lists the least expensive sourced instance with enough recorded GPU memory. Prices change; check before renting. Prefer a managed server? See <Link href="/hosting">dedicated hosting</Link>.</p></div>
      {!cloudModels.length ? <p className="fine-print">No supported NVIDIA variants with a recorded memory requirement are available.</p> : <div className="table-wrap"><table><thead><tr><th>Model</th><th>Recommended VRAM</th><th>Cheapest matching instance</th><th>Price</th><th>Source and date</th></tr></thead><tbody>{cloudModels.map(({ model, requirement, offer }) => <tr key={model.slug}>
        <td><Link href={`/models/${model.slug}/local`}>{model.name}</Link></td><td>{requirement} GB</td>
        {offer ? <><td>{publicCloudProviderName(offer.provider)} · {publicCloudInstanceName(offer.instance)}<div className="source-note">{publicCloudGpuName(offer.gpu)} · {offer.vram_gb} GB</div></td><td>{hourlyMoney(offer.usd_per_hour)}/h</td><td>{sourceUrl(offer.source) ? <a href={sourceUrl(offer.source)}>Price source · {dateText(offer.date)}</a> : <span>Source URL not supplied · {dateText(offer.date)}</span>}{offer.region ? ` · ${offer.region}` : ""}</td></> : <><td colSpan={3}>No matching sourced instance today.</td></>}
      </tr>)}</tbody></table></div>}
      <p className="mobile-scroll-hint">Swipe horizontally to see all cloud price and source details.</p>
    </section>

    <section className="section-wrap section" id="request"><div className="section-heading"><div><p className="section-kicker">Request a setup</p><h2>Tell us what you need</h2></div><p>Tell us the model, the expected volume and where the machine will run. We reply with a device recommendation and a quote. Final pricing depends on availability, shipping and VAT.</p></div>
      <div className="panel"><ContactForm models={models.filter((item) => item.installer_policy?.status !== "excluded").map((item) => ({ slug: item.slug, name: item.name }))} selectedModel={selectedSlug} /></div>
    </section>
  </>;
}
