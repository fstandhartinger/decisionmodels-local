import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CopyCommand } from "@/components/copy-command";
import { QuickStart } from "@/components/quick-start";
import { benchmarkRank, getModel, loadCatalog } from "@/lib/catalog";
import { dateText, loadHardwarePrices, money, suggestedDeviceFor } from "@/lib/hardware-data";

type PageProps = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return loadCatalog().map((model) => ({ slug: model.slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const model = getModel(slug);
  return model ? {
    title: `${model.name} local setup`,
    description: `Hardware requirements, licence details, and local setup for ${model.name}.`,
    openGraph: { images: ["/local/static/brand/og.png"] },
    alternates: { canonical: `/models/${model.slug}/local` }
  } : { title: "Model not found" };
}

function value(value: number | string | undefined | null, suffix = "") {
  return value === undefined || value === null || value === "" ? "—" : `${value}${suffix}`;
}

function safeJson(value: unknown) {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}

export default async function ModelLocalPage({ params }: PageProps) {
  const { slug } = await params;
  const model = getModel(slug);
  if (!model) notFound();
  const status = model.installer_policy?.status ?? "excluded";
  const excluded = status === "excluded";
  const commercialOnly = status === "supported_noncommercial_only";
  const jev = model.benchmarks?.jevbench;
  const image = model.benchmarks?.imagejevbench;
  const bench = jev ?? image;
  const benchmarkBadges = [
    jev ? { key: "jevbench", name: "JevBench Capability", rank: benchmarkRank(jev), version: jev.version, page: jev.page ?? "https://benchmarkheaven.com/jev-models" } : null,
    image ? { key: "imagejevbench", name: "ImageJevBench Capability", rank: benchmarkRank(image), version: image.version, page: image.page ?? "https://benchmarkheaven.com/image-jev-bench" } : null
  ].filter((item): item is NonNullable<typeof item> => item !== null);
  const prices = loadHardwarePrices();
  const cloudVariant = (model.variants ?? [])
    .filter((variant) => (variant.platforms ?? []).some((platform) => platform === "linux-nvidia" || platform === "wsl2-nvidia") && Number.isFinite(variant.recommended_vram_gb) && Number(variant.recommended_vram_gb) > 0)
    .sort((a, b) => Number(a.recommended_vram_gb) - Number(b.recommended_vram_gb))[0];
  const cloudRows = (prices.cloud ?? []).filter((row) => ["aws", "azure", "gcp"].includes(String(row.provider).toLowerCase()) && Number.isFinite(Number(row.vram_gb)) && Number(row.vram_gb) >= Number(cloudVariant?.recommended_vram_gb));
  const bestCloudRowByProvider = new Map<string, (typeof cloudRows)[number]>();
  for (const row of cloudRows) {
    const provider = String(row.provider).toLowerCase();
    const current = bestCloudRowByProvider.get(provider);
    if (!current || Number(row.usd_per_hour) < Number(current.usd_per_hour)) bestCloudRowByProvider.set(provider, row);
  }
  const cloudMemoryGb = cloudVariant ? Number(cloudVariant.recommended_vram_gb) : undefined;
  const cloudLines = [...bestCloudRowByProvider.values()].map((row) => {
    const provider = String(row.provider ?? "Cloud provider");
    const instance = String(row.instance ?? "instance not listed");
    const price = Number(row.usd_per_hour);
    const priceLabel = Number.isFinite(price) ? ` — ${money(price, "USD")}/h` : "";
    return { label: `${provider} ${instance}${priceLabel}${row.region ? ` · ${String(row.region)}` : ""}`, source: String(row.source ?? "#"), date: dateText(row.date), suggested: true };
  });
  const suggestion = suggestedDeviceFor(model, prices);
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: `${model.name} local setup`,
    applicationCategory: "DeveloperApplication",
    operatingSystem: (model.variants ?? []).flatMap((variant) => variant.platforms ?? []).join(", ") || "See supported variants",
    description: model.description ?? `Local setup information for ${model.name}.`,
    url: `https://decisionmodels.io/models/${model.slug}/local`,
    isAccessibleForFree: true
  };

  return <>
    <section className="section-wrap hero">
      <p className="eyebrow"><Link href="/local">Run locally</Link> / Model details</p>
      <div className="hero-grid">
        <div><h1>{model.name}</h1><p className="lede">{model.description ?? `${model.author ?? "Open-weight"} model${model.modalities?.length ? ` for ${model.modalities.join(" and ")}` : ""}.`}</p>
          <div className="model-meta space-top">
            <span className={`badge ${excluded ? "warn" : "signal"}`}>{excluded ? "Not installable" : commercialOnly ? "Non-commercial only" : "Local installer supported"}</span>
            {model.modalities?.map((modality) => <span className="badge" key={modality}>{modality}</span>)}
            {benchmarkBadges.length ? benchmarkBadges.map((item) => <a className={`badge ${item.rank !== null ? "signal" : ""}`} href={item.page} key={item.key}>{item.rank !== null ? `#${item.rank} ` : "No published rank · "}{item.name} ({item.version ?? "version not listed"} · {dateText(model.sources_checked_utc)})</a>) : <span className="badge">Benchmark row not listed</span>}
          </div>
        </div>
        <aside className="hero-note"><strong>Author: {model.author ?? "Not listed in the catalog"}</strong><span>{model.weights?.repo ? <a href={model.weights.url ?? `https://huggingface.co/${model.weights.repo}`}>Pinned weights source{model.weights.gated ? " · access may be gated" : ""}</a> : "Weights source not listed."}</span>
          <div className="source-note">Catalogue source checked: {dateText(model.sources_checked_utc)}{bench?.page ? <> · <a href={bench.page}>Benchmark row</a></> : null}</div>
        </aside>
      </div>
    </section>

    {excluded && <section className="section-wrap"><div className="callout muted"><strong>This model does not have a reviewed local install recipe.</strong><p>{model.installer_policy?.reason ?? "No local installer policy is recorded."} We will add an install command when a specific runtime and variant have been checked.</p></div></section>}
    {commercialOnly && <section className="section-wrap"><div className="callout"><strong>Personal and non-commercial use only.</strong><p>This installer entry is not cleared for commercial use. Read the model&apos;s licence evidence before downloading or serving it.</p></div></section>}

    <section className="section-wrap section">
      <div className="section-heading"><div><p className="section-kicker">Hardware</p><h2>Will it run on my machine?</h2></div><p>Requirements are recorded per variant. A dash means the catalogue does not provide that value.</p></div>
      {(model.variants?.length ?? 0) ? <div className="table-wrap"><table><thead><tr><th>Variant</th><th>Precision</th><th>Runtime</th><th>Benchmarked</th><th>Minimum / recommended VRAM</th><th>RAM</th><th>Disk</th><th>Platforms</th><th>Expected speed</th></tr></thead><tbody>
        {model.variants?.map((variant) => <tr key={variant.id ?? `${variant.runtime}-${variant.precision}`}><td>{variant.id ?? "Variant"}</td><td>{value(variant.precision)}</td><td>{value(variant.runtime)}{variant.runtime_version ? ` ${variant.runtime_version}` : ""}</td><td>{variant.benchmarked ? "Yes" : "No"}</td><td>{value(variant.min_vram_gb, " GB")} / {value(variant.recommended_vram_gb, " GB")}</td><td>{value(variant.min_ram_gb, " GB")}</td><td>{value(variant.disk_gb, " GB")}</td><td>{variant.platforms?.join(", ") || "—"}</td><td>{variant.measured?.source ? (variant.expected_speed ?? (variant.measured.p50_ms ? `${variant.measured.p50_ms} ms p50` : "Measured")) : "Not measured"}{variant.measured?.source ? <div className="source-note">Source: <a href={bench?.page ?? model.weights?.url ?? "https://benchmarkheaven.com/jev-models"}>{variant.measured.source}</a> · {dateText(model.sources_checked_utc)}</div> : null}</td></tr>)}
      </tbody></table></div> : <div className="callout muted"><strong>No installable variant is recorded.</strong><p>There are no memory, runtime, or speed figures to compare for this entry.</p></div>}
      {!excluded && <div className="command-line"><code>dm-local plan {model.slug}</code><CopyCommand value={`dm-local plan ${model.slug}`} /><span className="fine-print">Checks memory, disk, platform, and runtime against the catalog.</span></div>}
    </section>

    <section className="section-wrap section">
      <div className="section-heading"><div><p className="section-kicker">Quick start</p><h2>Choose where to run it</h2></div><p>Installer commands use the pinned model revision from the catalogue. Confirm the model terms before proceeding.</p></div>
      <QuickStart slug={model.slug} excluded={excluded} cloudLines={cloudLines} cloudMemoryGb={cloudMemoryGb} />
    </section>

    {!excluded && <section className="section-wrap section panel-grid">
      <article className="panel"><p className="section-kicker">Call your endpoint</p><h3>Use a local typed endpoint</h3><p>The response follows the same shape as the hosted Decision Models API.</p>
        <div className="command-line"><code>curl http://127.0.0.1:8484/v1/systemone</code><CopyCommand value={'curl -sS http://127.0.0.1:8484/v1/systemone -H "Content-Type: application/json" -d \'{"model":"' + model.slug + '","input":{"question":"Should we renew?","options":["yes","no"]}}\''} /></div>
        <p className="fine-print">Illustrative response format; sample probabilities are not a benchmark result.</p>
        <pre className="code-block">{`{"decision":"yes","probabilities":{"yes":0.82,"no":0.18},"model":"${model.slug}"}`}</pre>
        <div className="command-line"><code>python request snippet</code><CopyCommand value={`import requests\nresponse = requests.post(\n    "http://127.0.0.1:8484/v1/systemone",\n    json={"model": "${model.slug}", "input": {"question": "Should we renew?", "options": ["yes", "no"]}},\n    timeout=30,\n)\nprint(response.json())`} /></div>
        <Link href="https://decisionmodels.io/api" className="fine-print">Same shape as the hosted Decision Models API →</Link>
      </article>
      <article className="panel"><p className="section-kicker">Uninstall</p><h3>Remove the local files</h3><p>Use the installer to stop the service and remove this model&apos;s downloaded files.</p><div className="command-line"><code>dm-local uninstall {model.slug}</code><CopyCommand value={`dm-local uninstall ${model.slug}`} /></div></article>
    </section>}

    <section className="section-wrap section detail-grid">
      <div><div className="section-heading"><div><p className="section-kicker">Model terms</p><h2>Licence details</h2></div></div>
        <div className="panel"><div className="model-meta"><span className="badge">{model.licence?.spdx ?? "Licence not listed"}</span><span className="badge">Commercial use: {model.licence?.commercial_use ?? "not stated"}</span></div><p className="space-top-sm">{model.licence?.notes ?? "No licence summary is recorded for this model."}</p>
          {model.licence?.evidence?.length ? <p className="source-note">Evidence: {model.licence.evidence.map((url, index) => <span key={url}>{index ? " · " : ""}<a href={url}>{new URL(url).hostname}</a></span>)}</p> : null}
          {model.jev_distillation?.status && model.jev_distillation.status !== "none_found" ? <p className="variant-note"><strong>Jev-distillation note:</strong> {model.jev_distillation.evidence ?? `Status: ${model.jev_distillation.status}.`} {model.jev_distillation.url ? <a href={model.jev_distillation.url}>Source</a> : null}</p> : null}
          <p className="variant-note">The local installer has a separate <Link href="/local/licence">free and commercial licence</Link>.</p>
        </div>
      </div>
      <aside className="stack"><div className="panel"><p className="section-kicker">Pre-installed hardware</p><h3>{suggestion?.name ?? "Need a ready-to-run system?"}</h3><p>{suggestion ? `Memory: ${suggestion.memory_gb} GB. Indicative quote, excluding shipping and VAT.` : "No catalogued device currently meets a recorded supported variant."}</p>
        {suggestion ? <><p className="price">{suggestion.price_usd ? money(suggestion.price_usd, "USD") : suggestion.price_eur ? money(suggestion.price_eur, "EUR") : "Quote on request"}<span> indicative</span></p><p className="source-note">Street-price evidence: {suggestion.source.map((item, index) => <span key={`${item.source}-${index}`}>{index ? " · " : ""}<a href={item.source}>{item.currency} {item.value} · {dateText(item.date)}</a></span>)}</p></> : null}
        <Link href={`/hardware?model=${encodeURIComponent(model.slug)}`} className="button button-secondary">Ask about this model</Link></div>
      </aside>
    </section>

    <section className="section-wrap section">
      <div className="section-heading"><div><p className="section-kicker">Troubleshooting</p><h2>Common setup issues</h2></div></div>
      <div className="faq">
        {[ ["Driver or CUDA version is too old", "Update to a driver/runtime combination listed for the selected variant, then run dm-local plan again."], ["Out of memory", "Choose a smaller quantised variant when one is listed, or use a remote GPU with enough recommended memory."], ["NVIDIA Container Toolkit is missing", "Install and configure the NVIDIA Container Toolkit for your host before retrying the container runtime."], ["The port is already in use", "Stop the service using port 8484 or configure a different local port, then rerun the self-test."], ["A download was interrupted", "Run the install command again. Completed downloads resume when the artifact server supports range requests."], ["Checksum verification failed", "Do not use the file. Remove the incomplete download and retry from the pinned official source."], ["Apple Silicon memory pressure", "Close other memory-heavy apps and choose a smaller supported variant if the catalogue lists one."], ["WSL2 cannot see the GPU", "Check the Windows GPU driver and WSL2 GPU support, then verify `nvidia-smi` inside the WSL distribution."], ["SSH or firewall blocks the endpoint", "Keep the service on loopback and use an SSH tunnel. Avoid exposing the API port directly to the public internet."] ].map(([question, answer]) => <details className="disclosure" key={question}><summary>{question}</summary><p>{answer}</p></details>)}
      </div>
    </section>

    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: safeJson(structuredData) }} />
  </>;
}
