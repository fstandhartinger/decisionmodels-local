import type { Metadata } from "next";
import Link from "next/link";
import { ContactForm } from "@/components/contact-form";
import { loadCatalog } from "@/lib/catalog";
import { classRunsToday, cloudRequirement, dateText, hourlyMoney, loadDeviceClasses, loadHardwarePrices, money, publicCloudGpuName, publicCloudInstanceName, publicCloudProviderName, quoteSummary, sourceUrl, suggestedDeviceFor, cheapestCloudOptionFor } from "@/lib/hardware-data";
import { deviceDisplayName, type Device, type DeviceClass } from "@/lib/hardware-core.mjs";

export const metadata: Metadata = { alternates: { canonical: "/hardware" } };

type HardwareProps = { searchParams: Promise<{ model?: string }> };

const classFit: Record<string, string> = {
  "apple-silicon": "Mac mini and Mac Studio configurations. Unified memory is the installed memory for each listed configuration.",
  "gpu-workstation": "Complete desktop systems with a dedicated NVIDIA GPU.",
  gb10: "A 128 GB NVIDIA GB10 system. Compatibility is checked for each model on request.",
  jetson: "Compact NVIDIA edge systems for small quantised models.",
  android: "A high-end Android phone for small on-device models."
};

function HardwareQuoteCard({ device, definition, selected }: { device: Device; definition: DeviceClass; selected: boolean }) {
  const quotes = quoteSummary(device, definition);
  return <article className={`price-card ${selected ? "featured" : ""}`}>
    <p className="section-kicker">{definition.title}</p>
    <h3>{deviceDisplayName(device, definition)}</h3>
    <p>{classFit[definition.id] ?? "Compatibility depends on the model variant and memory requirement."}</p>
    <p className="variant-note">Memory: {typeof device.memory_gb === "number" && Number.isFinite(device.memory_gb) ? `${device.memory_gb} GB` : "Not listed"} {device.memory_kind ? `(${device.memory_kind})` : ""}</p>
    {quotes.map((item) => <div className="quote-card" key={item.currency}>
      <p className="price">{money(item.quote, item.currency)}<span> indicative</span></p>
      <p>Median sourced street price: {money(item.street, item.currency)} before the quote margin.</p>
      <p className="source-note">Price sources: {item.sources.map((source, index) => <span key={`${source.source}-${index}`}>{index ? " · " : ""}{sourceUrl(source.source) ? <a href={sourceUrl(source.source)}>{source.seller ?? "Price source"} — {money(source.value, source.currency)} · {dateText(source.date)}</a> : <span>Source link not supplied — {money(source.value, source.currency)} · {dateText(source.date)}</span>}</span>)}</p>
    </div>)}
    {!quotes.length && <p className="callout muted">No sourced price is available for this configuration. Ask us to confirm availability and pricing.</p>}
    {selected && <span className="badge signal">Suggested for your model</span>}
  </article>;
}

export default async function HardwarePage({ searchParams }: HardwareProps) {
  const { model: selectedSlug } = await searchParams;
  const models = loadCatalog();
  const selectedModel = selectedSlug ? models.find((item) => item.slug === selectedSlug) : undefined;
  const prices = loadHardwarePrices();
  const definitions = loadDeviceClasses();
  const devices = prices.devices ?? [];
  const selectedSuggestion = selectedModel ? suggestedDeviceFor(selectedModel, prices) : null;
  const suggestions = models.map((model) => ({ model, suggestion: suggestedDeviceFor(model, prices) })).filter((item): item is { model: typeof item.model; suggestion: NonNullable<typeof item.suggestion> } => item.suggestion !== null);
  const cloudModels = models.map((model) => ({ model, requirement: cloudRequirement(model), offer: cheapestCloudOptionFor(model, prices) })).filter((item) => item.requirement !== null);

  return <>
    <section className="section-wrap hero">
      <div className="hero-grid"><div><p className="eyebrow">Pre-installed hardware</p><h1>A local system, ready for your models.</h1><p className="lede">Compare sourced configurations, see which published model variants fit, and ask us to prepare a quote.</p></div>
        <aside className="hero-note"><strong>Local execution can keep inference data in your environment.</strong><span>Use your own network, access controls, retention policy, and deployment boundary. Downloads and other connected services still depend on your setup.</span></aside></div>
    </section>

    <section className="section-wrap section"><div className="benefit-grid">
      {[["Privacy", "Prompts and decisions stay inside your deployment boundary when the machine and service are configured locally."], ["Latency", "Inference does not need a network round trip to a hosted model. Measure it on your intended device."], ["Cost at scale", "Compare a known hardware purchase and operating cost with the per-call costs of hosted inference."], ["Offline and air-gapped", "After downloading model files, an isolated system can serve without an external model connection."]].map(([title, copy], index) => <article className="benefit" key={title}><span className="index">0{index + 1}</span><h3>{title}</h3><p>{copy}</p></article>)}
    </div></section>

    {selectedModel && <section className="section-wrap"><div className="callout"><strong>Selected model: {selectedModel.name}</strong><p>{selectedSuggestion?.name ?? "No listed configuration currently meets its recorded requirements."} Compatibility depends on the model variant and the target configuration.</p><Link href={`/models/${selectedModel.slug}/local`}>View model requirements →</Link></div></section>}

    <section className="section-wrap section">
      <div className="section-heading"><div><p className="section-kicker">Device classes</p><h2>Compare sourced hardware</h2></div><p>Prices use the median sourced street price in each currency. Indicative quotes add 30%, or at least 150 currency units, and round up to the next amount ending in 9. Shipping and VAT are excluded.</p></div>
      {definitions.map((definition) => {
        const members = devices.filter((device) => definition.device_ids.includes(device.id));
        return <div className="section hardware-class" key={definition.id}>
          <div className="section-heading"><div><h3>{definition.title}</h3><p className="fine-print">{classFit[definition.id]}</p></div><p>{classRunsToday(models, devices, definition)}</p></div>
          {definition.composition && <p className="callout muted class-composition">{definition.composition}</p>}
          {members.length ? <div className="model-grid">{members.map((device) => <HardwareQuoteCard key={device.id} device={device} definition={definition} selected={selectedSuggestion?.id === device.id} />)}</div> : <p className="fine-print">No sourced device entry is available for this class yet.</p>}
        </div>;
      })}
      <details className="disclosure"><summary>How we price this</summary><p>For each currency, we take the median of the sourced street prices, add 30% or at least 150 units, then round upward to an amount ending in 9. For GPU workstations, the street price includes the GPU card plus a USD 1,500 / EUR 1,400 base system: CPU, 64–128 GB RAM, 2 TB NVMe, PSU, and case. The final quote is confirmed by email.</p></details>
    </section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Model fit</p><h2>Which hardware for which model</h2></div><p>Suggestions choose the least expensive listed configuration that fits the smallest supported GPU or Apple Silicon variant. Device classes marked “on request” need a compatibility check.</p></div>
      {!suggestions.length ? <div className="callout muted"><strong>No model currently has a complete hardware recommendation.</strong><p>Suggestions appear when a supported variant has a matching platform, memory target, and sourced device price.</p></div> : <div className="table-wrap"><table><thead><tr><th>Model</th><th>Smallest fitting option</th><th>Indicative price</th><th>Details</th></tr></thead><tbody>{suggestions.map(({ model, suggestion }) => {
        const price = suggestion.price_usd ? money(suggestion.price_usd, "USD") : suggestion.price_eur ? money(suggestion.price_eur, "EUR") : "Price on request";
        return <tr key={model.slug}><td>{model.name}</td><td>{suggestion.name}<div className="source-note">{suggestion.memory_gb} GB {suggestion.memory_kind ?? "memory"}</div></td><td>{price}</td><td><Link href={`/models/${model.slug}/local`}>Model requirements →</Link></td></tr>;
      })}</tbody></table></div>}
    </section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Cloud and remote GPUs</p><h2>Use a GPU you already rent</h2></div><p>For each model, this lists the least expensive sourced instance with enough recorded GPU memory. Prices change; check before renting.</p></div>
      {!cloudModels.length ? <p className="fine-print">No supported NVIDIA variants with a recorded memory requirement are available.</p> : <div className="table-wrap"><table><thead><tr><th>Model</th><th>Recommended VRAM</th><th>Cheapest matching instance</th><th>Price</th><th>Source and date</th></tr></thead><tbody>{cloudModels.map(({ model, requirement, offer }) => <tr key={model.slug}>
        <td><Link href={`/models/${model.slug}/local`}>{model.name}</Link></td><td>{requirement} GB</td>
        {offer ? <><td>{publicCloudProviderName(offer.provider)} · {publicCloudInstanceName(offer.instance)}<div className="source-note">{publicCloudGpuName(offer.gpu)} · {offer.vram_gb} GB</div></td><td>{hourlyMoney(offer.usd_per_hour)}/h</td><td><a href={offer.source ?? "#"}>Price source · {dateText(offer.date)}</a>{offer.region ? ` · ${offer.region}` : ""}</td></> : <><td colSpan={3}>No matching sourced instance today.</td></>}
      </tr>)}</tbody></table></div>}
      <p className="source-note">Availability, region, storage, and egress can change the total cost. Check the provider’s current listing before renting.</p>
    </section>

    <section className="section-wrap section" id="request"><div className="section-heading"><div><p className="section-kicker">Request a setup</p><h2>Tell us what you need</h2></div><p>We will check the requested configuration and reply with an indicative quote. Final pricing depends on availability, shipping, and VAT.</p></div>
      <div className="panel"><ContactForm models={models.map((item) => ({ slug: item.slug, name: item.name }))} selectedModel={selectedSlug} /></div>
    </section>
  </>;
}
