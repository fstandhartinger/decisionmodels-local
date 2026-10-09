import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CopyCommand } from "@/components/copy-command";
import { QuickStart } from "@/components/quick-start";
import { benchmarkRank, getModel, hasAnyExecutableInstallRecipe, installRecipeStatus, loadCatalog, sanitizePublicText, type Model, type ModelVariant } from "@/lib/catalog";
import { cloudOptionsFor, cloudRequirement, dateText, hourlyMoney, loadHardwarePrices, money, publicCloudInstanceName, publicCloudProviderName, sourcePublisher, sourceUrl, suggestedDeviceFor } from "@/lib/hardware-data";

type PageProps = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return loadCatalog().map((model) => ({ slug: model.slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const model = getModel(slug);
  const excluded = model?.installer_policy?.status === "excluded";
  const hasRecipe = model ? hasAnyExecutableInstallRecipe(model) : false;
  return model ? {
    title: excluded ? "Model not offered" : hasRecipe ? `${model.name} local setup` : `${model.name} setup in preparation`,
    description: excluded ? "This model is not offered in the installer while its licensing review is pending." : hasRecipe ? `Hardware requirements, licence details, and local setup for ${model.name}.` : `An executable local install recipe for ${model.name} is in preparation.`,
    ...(excluded ? { robots: { index: false, follow: false } } : {}),
    openGraph: { images: ["/local/static/brand/og.png"] },
    alternates: { canonical: `/models/${model.slug}/local` }
  } : { title: "Model not found" };
}

function value(value: number | string | undefined | null, suffix = "") {
  return value === undefined || value === null || value === "" ? "—" : `${value}${suffix}`;
}

function vramValue(variant: ModelVariant, amount: number | undefined) {
  const context = `${variant.runtime ?? ""} ${(variant.platforms ?? []).join(" ")}`.toLowerCase();
  if (amount === 0 && /cpu|mlx|mps|macos-arm64|linux-cpu|windows-cpu/.test(context)) return "Uses system/unified RAM";
  return value(amount, " GB");
}

function runtimeLabel(variant: ModelVariant) {
  const runtime = variant.runtime?.match(/vllm|mlx(?:_vlm)?|pytorch|transformers|llama\.cpp|ollama|onnx/i)?.[0];
  if (!runtime) return "See model card";
  const names: Record<string, string> = { vllm: "vLLM", mlx: "MLX", mlx_vlm: "MLX VLM", pytorch: "PyTorch", transformers: "Transformers", ollama: "Ollama", onnx: "ONNX" };
  const version = variant.runtime_version?.match(/^(?:torch\s+)?(\d+\.\d+(?:\.\d+)?(?:\+[a-z0-9]+)?)(?:\s|$)/i)?.[1];
  return `${names[runtime.toLowerCase()] ?? runtime}${version ? ` ${version}` : ""}`;
}

function safeJson(value: unknown) {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}

function shortRevision(revision?: string) {
  return revision ? revision.slice(0, 8) : "revision not listed";
}

function modelSummary(model: Model) {
  const size = model.params?.total_b ? `${model.params.total_b}B ` : "";
  const modality = model.modalities?.length ? model.modalities.join(" and ") : "open-weight";
  return `${size}${modality} model.`;
}

function shortGpuName(value?: string) {
  if (!value || /unverified/i.test(value)) return null;
  const match = value.match(/RTX\s+PRO\s+6000|RTX\s+5090|RTX\s+4090|H100|H200|L40S|A100|H20/i);
  return match?.[0]?.toUpperCase().replace("RTX PRO", "RTX PRO") ?? null;
}

function speedLabel(model: Model, variant: ModelVariant) {
  const benchmarks = model.modalities?.includes("image")
    ? [model.benchmarks?.imagejevbench, model.benchmarks?.jevbench]
    : [model.benchmarks?.jevbench, model.benchmarks?.imagejevbench];
  const benchmark = benchmarks.find((item) => Number.isFinite(item?.p50_s_raw));
  const gpu = shortGpuName(variant.measured?.gpu);
  if (gpu && Number.isFinite(benchmark?.p50_s_raw)) {
    const seconds = Number(benchmark?.p50_s_raw);
    const time = seconds < 0.1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(1)} s`;
    return `~${time} per decision on a GPU (measured by Benchmark Heaven on ${gpu}).`;
  }
  if (variant.expected_speed) return sanitizePublicText(variant.expected_speed);
  return "Timing is not reported for this variant.";
}

function installStatusLabel(variant: ModelVariant) {
  const status = installRecipeStatus(variant);
  if (status === "tested") return "Tested install recipe";
  if (status === "ready_unverified") return "Recipe ready · unverified";
  return "Documentation only";
}

function commercialLabel(value?: string) {
  if (value === "yes") return "yes";
  if (value === "no") return "no";
  if (value === "conditional") return "conditional";
  return "not stated";
}

function commercialCopy(value?: string) {
  if (value === "yes") return "Commercial use is allowed by the model’s listed licence.";
  if (value === "no") return "The model’s listed licence does not allow commercial use.";
  if (value === "conditional") return "Commercial use is conditional; review the model card for the terms.";
  return "Commercial use is not stated in the catalogue; review the model card for the terms.";
}

function apiRequest() {
  return `curl http://127.0.0.1:8484/v1/systemone -H 'Content-Type: application/json' -d '{"state":"Mia owns a red bicycle.","questions":{"color":{"type":"choice","instructions":"Which color is the bicycle?","criteria":{"red":null,"blue":null}}}}'`;
}

function apiOutput(slug: string) {
  return `{"id":"dec_…","model":"${slug}","answers":{"color":{"type":"choice","choice":"red","confidence":0.97,"probabilities":{"red":0.97,"blue":0.03}}},"usage":{"input_tokens":64,"output_tokens":0,"decisions":1}}`;
}

function pythonExample() {
  return `import json
import urllib.request
payload = {"state": "Mia owns a red bicycle.",
           "questions": {"color": {"type": "choice", "instructions": "Which color is the bicycle?", "criteria": {"red": None, "blue": None}}}}
request = urllib.request.Request("http://127.0.0.1:8484/v1/systemone", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=30) as response:
    result = json.load(response)
print(result["answers"]["color"])`;
}

function multimodalRequest() {
  return `curl http://127.0.0.1:8484/v1/multimodal -H 'Content-Type: application/json' -d '{"state":"Read the image and answer the question.","images":["data:image/png;base64,…"],"questions":{"object":{"type":"choice","instructions":"What is shown?","criteria":{"bicycle":null,"car":null}}}}'`;
}

export default async function ModelLocalPage({ params }: PageProps) {
  const { slug } = await params;
  const model = getModel(slug);
  if (!model) notFound();
  const status = model.installer_policy?.status ?? "excluded";
  const excluded = status === "excluded";
  if (excluded) return <section className="section-wrap narrow page-top"><p className="eyebrow"><Link href="/local">Run locally</Link></p><h1>Model not offered</h1><p className="lede space-top">This model is not offered in the installer while its licensing review is pending.</p></section>;
  const commercialOnly = status === "supported_noncommercial_only";
  const hasRecipe = hasAnyExecutableInstallRecipe(model);
  const recipeTested = (model.variants ?? []).some((variant) => installRecipeStatus(variant) === "tested");
  const benchmarkBadges = [
    model.benchmarks?.jevbench ? { label: "JevBench", data: model.benchmarks.jevbench } : null,
    model.benchmarks?.imagejevbench ? { label: "ImageJevBench", data: model.benchmarks.imagejevbench } : null
  ].filter((item): item is NonNullable<typeof item> => item !== null);
  const prices = loadHardwarePrices();
  const requiredVram = cloudRequirement(model);
  const providerOffers = new Map<string, NonNullable<ReturnType<typeof cloudOptionsFor>>[number]>();
  for (const offer of cloudOptionsFor(model, prices)) {
    const provider = String(offer.provider ?? "").toLowerCase();
    const current = providerOffers.get(provider);
    if (!current || Number(offer.usd_per_hour) < Number(current.usd_per_hour)) providerOffers.set(provider, offer);
  }
  const cloudLines = [...providerOffers.values()].map((offer) => ({
    label: `${publicCloudProviderName(offer.provider)} · ${publicCloudInstanceName(offer.instance)} · ${offer.vram_gb} GB · ${hourlyMoney(offer.usd_per_hour)}/h`,
    source: String(offer.source ?? "#"),
    date: dateText(offer.date)
  }));
  const suggestion = suggestedDeviceFor(model, prices);
  const weightRevisionUrl = model.weights?.repo && model.weights.revision
    ? `https://huggingface.co/${model.weights.repo}/tree/${model.weights.revision}`
    : model.weights?.url;
  const modelCardUrl = model.weights?.repo ? `https://huggingface.co/${model.weights.repo}` : model.weights?.url;
  const benchmarkHome = benchmarkBadges[0]?.data.page ?? "https://benchmarkheaven.com/jev-models";
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: `${model.name} local setup`,
    applicationCategory: "DeveloperApplication",
    operatingSystem: (model.variants ?? []).flatMap((variant) => variant.platforms ?? []).join(", ") || "See supported variants",
    description: `Local setup information for ${model.name}, a ${modelSummary(model)}`,
    url: `https://decisionmodels.io/models/${model.slug}/local`,
    isAccessibleForFree: true
  };

  return <>
    <section className="section-wrap hero">
      <p className="eyebrow"><Link href="/local">Run locally</Link> / Model details</p>
      <div className="hero-grid">
        <div><h1>{model.name}</h1><p className="lede">{modelSummary(model)}</p>
          <div className="model-meta space-top">
            <span className={`badge ${hasRecipe && recipeTested ? "signal" : ""}`}>{!hasRecipe ? "Setup in preparation" : recipeTested ? "Install tested" : "Recipe ready · unverified"}</span>
            {commercialOnly && <span className="badge warn">Non-commercial only</span>}
            {model.modalities?.map((modality) => <span className="badge" key={modality}>{modality}</span>)}
            {benchmarkBadges.map(({ label, data }) => {
              const rank = benchmarkRank(data);
              const page = data.page ?? (label === "JevBench" ? "https://benchmarkheaven.com/jev-models" : "https://benchmarkheaven.com/image-jev-bench");
              return <a className={`badge ${rank !== null ? "signal" : ""}`} href={page} key={label}>{rank !== null ? `#${rank} on ${label} (Capability, ${data.version ?? "version not listed"})` : `${label} Capability score · ${data.version ?? "version not listed"}`}</a>;
            })}
          </div>
        </div>
        <aside className="hero-note"><strong>Weights:</strong>
          {model.weights?.repo ? <span><a href={weightRevisionUrl}>{model.weights.repo} @ {shortRevision(model.weights.revision)}</a>{model.weights.gated ? " · access may be gated" : ""}</span> : <span>Model repository not listed</span>}
          <div className="source-note">Benchmark: <a href={benchmarkHome}>Benchmark Heaven</a></div>
        </aside>
      </div>
    </section>

    {commercialOnly && <section className="section-wrap"><div className="callout"><strong>Personal and non-commercial use only.</strong><p>This installer entry is not cleared for commercial use. Read the model card before downloading or serving it.</p></div></section>}

    <section className="section-wrap section">
      <div className="section-heading"><div><p className="section-kicker">Hardware</p><h2>Will it run on my machine?</h2></div><p>Requirements are recorded per variant. A dash means the catalogue does not provide that value.</p></div>
      {(model.variants?.length ?? 0) ? <>
        <div className="variant-table table-wrap"><table><thead><tr><th>Variant</th><th>Precision</th><th>Runtime</th><th>Benchmarked</th><th>Install recipe</th><th>Minimum / recommended VRAM</th><th>RAM</th><th>Disk</th><th>Platforms</th><th>Expected speed</th></tr></thead><tbody>{model.variants?.map((variant) => <tr key={variant.id ?? `${variant.runtime}-${variant.precision}`}><td>{variant.id ?? "Variant"}</td><td>{value(variant.precision)}</td><td>{runtimeLabel(variant)}</td><td>{variant.benchmarked ? "Yes" : "No"}</td><td>{installStatusLabel(variant)}</td><td>{vramValue(variant, variant.min_vram_gb)} / {vramValue(variant, variant.recommended_vram_gb)}</td><td>{value(variant.min_ram_gb, " GB")}</td><td>{value(variant.disk_gb, " GB")}</td><td>{variant.platforms?.join(", ") || "—"}</td><td>{speedLabel(model, variant)}</td></tr>)}</tbody></table></div>
        <div className="variant-cards">{model.variants?.map((variant) => <article className="panel variant-card" key={variant.id ?? `${variant.runtime}-${variant.precision}`}>
          <div className="model-meta"><span className="badge signal">{variant.id ?? "Variant"}</span><span className="badge">{value(variant.precision)}</span></div>
          <dl><div><dt>Runtime</dt><dd>{runtimeLabel(variant)}</dd></div><div><dt>Install recipe</dt><dd>{installStatusLabel(variant)}</dd></div><div><dt>VRAM</dt><dd>{vramValue(variant, variant.min_vram_gb)} minimum / {vramValue(variant, variant.recommended_vram_gb)} recommended</dd></div><div><dt>RAM</dt><dd>{value(variant.min_ram_gb, " GB")}</dd></div><div><dt>Disk</dt><dd>{value(variant.disk_gb, " GB")}</dd></div><div><dt>Platforms</dt><dd>{variant.platforms?.join(", ") || "—"}</dd></div><div><dt>Expected speed</dt><dd>{speedLabel(model, variant)}</dd></div></dl>
        </article>)}</div>
      </> : <div className="callout muted"><strong>No installable variant is recorded.</strong><p>There are no memory, runtime, or speed figures to compare for this entry.</p></div>}
      {hasRecipe && <div className="command-line"><code>dm-local plan {model.slug}</code><CopyCommand value={`dm-local plan ${model.slug}`} /><span className="fine-print">Checks memory, disk, platform, and runtime against the catalogue.</span></div>}
    </section>

    <section className="section-wrap section">
      <div className="section-heading"><div><p className="section-kicker">Quick start</p><h2>Choose where to run it</h2></div><p>Installer commands use the pinned model revision. Confirm the model terms before proceeding.</p></div>
      <QuickStart slug={model.slug} excluded={excluded} hasRecipe={hasRecipe} recipeTested={recipeTested} cloudLines={cloudLines} cloudMemoryGb={requiredVram ?? undefined} />
    </section>

    {!excluded && hasRecipe && <section className="section-wrap section panel-grid">
      <article className="panel api-examples"><p className="section-kicker">Call your endpoint</p><h3>Use a local typed endpoint</h3><p>The API accepts typed questions and returns typed answers with probabilities.</p>
        <h4>Request</h4><pre className="code-block">{apiRequest()}</pre>
        <h4>Example output</h4><pre className="code-block">{apiOutput(model.slug)}</pre>
        <h4>Python</h4><pre className="code-block">{pythonExample()}</pre>
        {model.modalities?.includes("image") && <><h4>Image input</h4><pre className="code-block">{multimodalRequest()}</pre></>}
        <Link href="https://decisionmodels.io/api" className="fine-print">Read the hosted API reference →</Link>
      </article>
      <article className="panel"><p className="section-kicker">Uninstall</p><h3>Remove the local files</h3><p>Use the installer to stop the service and remove this model&apos;s downloaded files.</p><div className="command-line"><code>dm-local uninstall {model.slug}</code><CopyCommand value={`dm-local uninstall ${model.slug}`} /></div></article>
    </section>}

    {hasRecipe && <section className="section-wrap section detail-grid">
      <div><div className="section-heading"><div><p className="section-kicker">Model terms</p><h2>Licence details</h2></div></div>
        <div className="panel"><div className="model-meta"><span className="badge">{model.licence?.spdx ?? "Licence not listed"}</span><span className="badge">Commercial use: {commercialLabel(model.licence?.commercial_use)}</span></div>
          <p className="space-top-sm">{commercialCopy(model.licence?.commercial_use)}</p>
          {modelCardUrl && <p className="source-note"><a href={modelCardUrl}>Model card</a></p>}
          {model.jev_distillation?.display_note ? <p className="variant-note">{model.jev_distillation.display_note}</p> : model.jev_distillation?.status === "stated" ? <p className="variant-note">The model card states that this model was trained using Jev outputs.</p> : null}
          <p className="variant-note">The local installer has a separate <Link href="/local/licence">free and commercial licence</Link>.</p>
        </div>
      </div>
      <aside className="stack"><div className="panel"><p className="section-kicker">Pre-installed hardware</p><h3>{suggestion?.name ?? "Need a ready-to-run system?"}</h3><p>{suggestion ? `Memory: ${suggestion.memory_gb} GB. Indicative quote, excluding shipping and VAT.` : "No listed configuration currently meets a supported variant."}</p>
        {suggestion ? <><p className="variant-note">{suggestion.install_status === "tested" ? "Model recipe tested on other hardware; this device is a fit estimate." : "Recipe ready but unverified; this device is a fit estimate."}</p><p className="price">{suggestion.price_usd ? money(suggestion.price_usd, "USD") : suggestion.price_eur ? money(suggestion.price_eur, "EUR") : "Quote on request"}<span> indicative</span></p><details className="price-source-disclosure"><summary>Price sources ({suggestion.source.length})</summary><ul className="price-source-list">{suggestion.source.map((item, index) => <li key={`${item.source}-${index}`}>{sourceUrl(item.source) ? <a href={sourceUrl(item.source)}>{sourcePublisher(item.source)} · {dateText(item.date)}</a> : <span>Source URL not supplied · {dateText(item.date)}</span>}</li>)}</ul></details></> : null}
        <Link href={`/hardware?model=${encodeURIComponent(model.slug)}`} className="button button-secondary">See hardware options</Link></div>
      </aside>
    </section>}

    <section className="section-wrap section">
      <div className="section-heading"><div><p className="section-kicker">Troubleshooting</p><h2>Common setup issues</h2></div></div>
      <div className="faq">
        {[["Driver or CUDA version is too old", "Update to a driver/runtime combination listed for the selected variant, then run dm-local plan again."], ["Out of memory", "Choose a smaller quantised variant when one is listed, or use a remote GPU with enough recommended memory."], ["NVIDIA Container Toolkit is missing", "Install and configure the NVIDIA Container Toolkit for your host before retrying the container runtime."], ["The port is already in use", "Stop the service using port 8484 or configure a different local port, then rerun the self-test."], ["A download was interrupted", "Run the install command again. Completed downloads resume when the artifact server supports range requests."], ["Checksum verification failed", "Do not use the file. Remove the incomplete download and retry from the pinned official source."], ["Apple Silicon memory pressure", "Close other memory-heavy apps and choose a smaller supported variant if the catalogue lists one."], ["WSL2 cannot see the GPU", "Check the Windows GPU driver and WSL2 GPU support, then verify nvidia-smi inside the WSL distribution."], ["SSH or firewall blocks the endpoint", "Keep the service on loopback and use an SSH tunnel. Avoid exposing the API port directly to the public internet."]].map(([question, answer]) => <details className="disclosure" key={question}><summary>{question}</summary><p>{answer}</p></details>)}
      </div>
    </section>

    {hasRecipe && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: safeJson(structuredData) }} />}
  </>;
}
