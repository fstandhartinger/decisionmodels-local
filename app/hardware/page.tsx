import type { Metadata } from "next";
import Link from "next/link";
import { ContactForm } from "@/components/contact-form";
import { loadCatalog } from "@/lib/catalog";
import { dateText, loadHardwarePrices, money, quoteSummary, suggestedDeviceFor } from "@/lib/hardware-data";

export const metadata: Metadata = { alternates: { canonical: "/hardware" } };

type HardwareProps = { searchParams: Promise<{ model?: string }> };

const classCopy: Record<string, { title: string; fit: string }> = {
  jetson: { title: "Jetson edge systems", fit: "Compact edge deployments. Jetson and Android suggestions are limited to small quantised variants." },
  "apple-silicon": { title: "Mac mini and Mac Studio", fit: "Unified-memory systems for catalogued variants that list macOS or compatible runtimes." },
  gb10: { title: "DGX Spark and GB10 systems", fit: "A local development system for variants whose recorded memory fits the device." },
  "gpu-workstation": { title: "RTX workstation", fit: "Dedicated GPU memory for supported NVIDIA runtime variants." },
  "amd-apu": { title: "AMD unified-memory systems", fit: "High-memory systems without CUDA; use only with a catalogued compatible runtime." },
  android: { title: "Android devices", fit: "Small on-device quantised models where a compatible runtime and memory are recorded." }
};

function HardwareQuoteCard({ device, selected }: { device: NonNullable<ReturnType<typeof loadHardwarePrices>["devices"]>[number]; selected: boolean }) {
  const quotes = quoteSummary(device);
  const title = classCopy[device.class]?.title ?? device.class.replaceAll("-", " ");
  return <article className={`price-card ${selected ? "featured" : ""}`}>
    <p className="section-kicker">{title}</p><h3>{device.name}</h3>
    <p>{classCopy[device.class]?.fit ?? "Compatibility depends on the catalogued runtime and memory requirements."}</p>
    <p className="variant-note">Memory: {Number.isFinite(device.memory_gb) ? `${device.memory_gb} GB` : "Not listed"} {device.memory_kind ? `(${device.memory_kind})` : ""}{device.gpu ? ` · ${device.gpu}` : ""}</p>
    {device.prices?.[0] && <p className="source-note">Specification/pricing record: <a href={device.prices[0].source}>{device.prices[0].seller ?? device.name} · {dateText(device.prices[0].date)}</a></p>}
    {quotes.map((item) => <div className="quote-card" key={item.currency}>
      <p className="price">{money(item.quote, item.currency)}<span> indicative quote</span></p>
      <p>Street-price median: {money(item.street, item.currency)}. Includes setup and pre-install margin.</p>
      <p className="source-note">Sources and dates: {item.sources.map((source, index) => <span key={`${source.source}-${index}`}>{index ? " · " : ""}<a href={source.source}>{source.seller ?? source.source} — {money(source.value, source.currency)} · {dateText(source.date)}</a></span>)}</p>
    </div>)}
    {!quotes.length && <p className="callout muted">No verified street price is available in this catalog. Request a quote for current availability.</p>}
    {device.notes && <details className="disclosure"><summary>Price and specification notes</summary><p>{device.notes}</p></details>}
    {selected && <span className="badge signal">Selected for your model</span>}
  </article>;
}

export default async function HardwarePage({ searchParams }: HardwareProps) {
  const { model: selectedSlug } = await searchParams;
  const models = loadCatalog();
  const selectedModel = selectedSlug ? models.find((item) => item.slug === selectedSlug) : undefined;
  const prices = loadHardwarePrices();
  const devices = prices.devices ?? [];
  const classes = [...new Set(devices.map((device) => device.class))];
  const suggestions = models.map((model) => ({ model, suggestion: suggestedDeviceFor(model, prices) })).filter((item) => item.suggestion);
  const cloud = prices.cloud ?? [];
  return <>
    <section className="section-wrap hero">
      <div className="hero-grid"><div><p className="eyebrow">Pre-installed hardware</p><h1>A local system, ready for your models.</h1><p className="lede">Choose a device class from sourced street prices, then tell us where it will run. We will confirm compatibility and prepare a quote.</p></div>
        <aside className="hero-note"><strong>Local execution can keep inference data in your environment.</strong><span>Use your own network, access controls, retention policy, and deployment boundary. Downloads and other connected services still depend on your setup.</span></aside></div>
    </section>

    <section className="section-wrap section"><div className="benefit-grid">
      {[ ["Privacy", "Prompts and decisions stay inside your deployment boundary when the machine and service are configured locally."], ["Latency", "Inference does not need a network round trip to a hosted model. Measure it on your intended device."], ["Cost at scale", "Compare a known hardware purchase and operating cost with the per-call costs of hosted inference."], ["Offline and air-gapped", "After downloading model files, an isolated system can serve without an external model connection." ] ].map(([title, text], index) => <article className="benefit" key={title}><span className="index">0{index + 1}</span><h3>{title}</h3><p>{text}</p></article>)}
    </div></section>

    {selectedModel && <section className="section-wrap"><div className="callout"><strong>Selected model: {selectedModel.name}</strong><p>{suggestedDeviceFor(selectedModel, prices)?.name ?? "No priced device is currently suggested for this model."} Compatibility depends on a reviewed model variant and the target&apos;s full configuration.</p><Link href={`/models/${selectedModel.slug}/local`}>View model requirements →</Link></div></section>}

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Device classes</p><h2>Compare sourced hardware</h2></div><p>Quotes use the median price in each currency, plus 30% or at least 150 units, rounded up to the next 9. Shipping and VAT are excluded.</p></div>
      {classes.map((deviceClass) => <div className="section" key={deviceClass}><div className="section-heading"><h3>{classCopy[deviceClass]?.title ?? deviceClass.replaceAll("-", " ")}</h3><p>{classCopy[deviceClass]?.fit}</p></div><div className="model-grid">{devices.filter((device) => device.class === deviceClass).map((device) => <HardwareQuoteCard key={device.id} device={device} selected={Boolean(selectedModel && suggestedDeviceFor(selectedModel, prices)?.id === device.id)} />)}</div></div>)}
      <details className="disclosure"><summary>How we price this</summary><p>For each currency, we take the median of the sourced street prices in the catalog. The indicative quote is 1.30× that median, with a minimum increase of 150 in the same currency, rounded upward to an amount ending in 9. Street-price sources and retrieved dates are listed on each card. The final quote is confirmed by email.</p><p className="source-note">Source: Decision Models hardware quote method · checked 9 October 2026.</p></details>
    </section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Model fit</p><h2>Start with the model&apos;s memory target</h2></div><p>Suggestions use the smallest supported variant with a recorded recommended memory. Unsupported or incomplete entries receive no device recommendation.</p></div>
      {!suggestions.length ? <div className="callout muted"><strong>No model currently has a complete hardware recommendation.</strong><p>Each model page will show a device once its variant requirements and a sourced hardware price are available.</p></div> : <div className="table-wrap"><table><thead><tr><th>Model</th><th>Suggested device</th><th>Indicative price</th><th>Installer policy</th></tr></thead><tbody>{suggestions.map(({ model, suggestion }) => <tr key={model.slug}><td><Link href={`/models/${model.slug}/local`}>{model.name}</Link></td><td><Link href={`/hardware?model=${model.slug}`}>{suggestion?.name}</Link></td><td>{suggestion?.price_usd ? money(suggestion.price_usd, "USD") : suggestion?.price_eur ? money(suggestion.price_eur, "EUR") : "Not available"}<div className="source-note">Price evidence: {suggestion?.source.map((source, index) => <span key={`${source.source}-${index}`}>{index ? " · " : ""}<a href={source.source}>{source.currency} · {dateText(source.date)}</a></span>)}</div></td><td>{model.installer_policy?.status ?? "not recorded"}</td></tr>)}</tbody></table></div>}
    </section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Cloud and remote nodes</p><h2>Use a GPU you already rent</h2></div><p>Hourly prices below come from the current hardware-price research file. They are indicative and may differ by region, tier, storage, and egress.</p></div>
      {!cloud.length ? <p className="fine-print">No sourced cloud prices are available in the current catalog.</p> : <div className="table-wrap"><table><thead><tr><th>Provider</th><th>Instance</th><th>GPU / VRAM</th><th>Indicative hourly price</th><th>Source and date</th></tr></thead><tbody>{cloud.map((row, index) => <tr key={`${row.provider}-${row.instance}-${index}`}><td>{String(row.provider ?? "—")}</td><td>{String(row.instance ?? "—")}</td><td>{String(row.gpu ?? "—")}{row.vram_gb ? ` · ${row.vram_gb} GB` : ""}</td><td>{Number.isFinite(Number(row.usd_per_hour)) ? `${money(Number(row.usd_per_hour), "USD")}/h` : "Not listed"}</td><td><a href={String(row.source ?? "#")}>{String(row.source ?? "Source not listed")}</a> · {dateText(row.date)}{row.region ? ` · ${String(row.region)}` : ""}</td></tr>)}</tbody></table></div>}
      <p className="source-note">Check instance availability and total charges before creating a cloud resource. Storage and egress may be billed separately.</p>
    </section>

    <section className="section-wrap section" id="request"><div className="section-heading"><div><p className="section-kicker">Request a setup</p><h2>Tell us what you need</h2></div><p>We will check the requested configuration and reply with an indicative quote. Final pricing depends on availability, shipping, and VAT.</p></div>
      <div className="panel"><ContactForm models={models.map((item) => ({ slug: item.slug, name: item.name }))} selectedModel={selectedSlug} /></div>
    </section>
  </>;
}
