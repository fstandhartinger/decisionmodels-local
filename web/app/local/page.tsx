import type { Metadata } from "next";
import Link from "next/link";
import { CopyCommand } from "@/components/copy-command";
import { benchmarkRank, hasAnyExecutableInstallRecipe, installRecipeStatus, loadCatalog, sortedByBenchmark, type Model } from "@/lib/catalog";
import { loadHardwarePrices, suggestedDeviceFor } from "@/lib/hardware-data";

export const metadata: Metadata = { alternates: { canonical: "/local" } };

type BenchmarkField = "jevbench" | "imagejevbench";

function smallestHardware(model: Model) {
  const variants = (model.variants ?? []).filter((variant) => installRecipeStatus(variant) !== "documentation_only");
  if (!variants.length) return ["Setup in preparation"];
  const chips: string[] = [];
  const label = (platform: "linux-nvidia" | "macos-arm64" | "linux-cpu" | "windows-cpu") => {
    const option = variants.filter((variant) => variant.platforms?.includes(platform)).sort((a, b) => {
      const memory = (variant: typeof a) => platform === "linux-nvidia" ? variant.min_vram_gb ?? Infinity : variant.min_ram_gb ?? Infinity;
      return memory(a) - memory(b);
    })[0];
    if (!option) return null;
    const state = installRecipeStatus(option) === "tested" ? "install tested" : "estimate · unverified";
    if (platform === "linux-nvidia") {
      const memory = option.min_vram_gb;
      if (!memory) return `GPU · ${state}`;
      return `${memory <= 24 ? "RTX 4090" : memory <= 32 ? "RTX 5090" : "GPU"}, ${memory} GB+ · ${state}`;
    }
    return `${platform === "macos-arm64" ? "Mac" : "CPU"}${option.min_ram_gb ? `, ${option.min_ram_gb} GB RAM` : ""} · ${state}`;
  };
  const gpuLabel = label("linux-nvidia");
  const macLabel = label("macos-arm64");
  const cpuLabel = label("linux-cpu") ?? label("windows-cpu");
  if (gpuLabel) chips.push(gpuLabel);
  if (macLabel) chips.push(macLabel);
  if (cpuLabel) chips.push(cpuLabel);
  return chips.length ? chips : ["Hardware requirements on model page"];
}

function commercialBadge(model: Model) {
  const use = model.licence?.commercial_use;
  if (use === "yes") return { label: "Commercial use", tone: "signal" };
  if (use === "no") return { label: "Non-commercial", tone: "warn" };
  if (use === "conditional") return { label: "Conditional terms", tone: "warn" };
  return { label: "Licence not stated", tone: "" };
}

function modelSummary(model: Model) {
  const size = model.params?.total_b ? `${model.params.total_b}B ` : "";
  const modality = model.modalities?.length ? model.modalities.join(" and ") : "open-weight";
  return `${size}${modality} model.`;
}

function ModelCard({ model, field, excluded = false }: { model: Model; field: BenchmarkField; excluded?: boolean }) {
  const benchmark = model.benchmarks?.[field];
  const rank = benchmarkRank(benchmark);
  const score = benchmark?.capability;
  const badge = commercialBadge(model);
  const size = model.params?.total_b ? `${model.params.total_b}B` : "Size not listed";
  const benchmarkPage = benchmark?.page ?? (field === "jevbench" ? "https://benchmarkheaven.com/jev-models" : "https://benchmarkheaven.com/image-jev-bench");
  if (excluded) return <article className="model-card excluded-model-card"><strong>Model not offered</strong><p>This model is not offered in the installer while its licensing review is pending.</p></article>;
  return <article className={`model-card ranked-model-card ${excluded ? "excluded-model-card" : ""}`}>
    <div className="model-meta"><a className={`badge ${rank !== null ? "signal" : ""}`} href={benchmarkPage}>{rank !== null ? `#${rank}` : "Rank not listed"}</a><span className="badge">{size}</span><span className={`badge ${badge.tone}`}>{badge.label}</span></div>
    <h3><Link href={`/models/${model.slug}/local`}>{model.name}</Link></h3>
    <p className="capability-score">{Number.isFinite(score) ? `Capability score ${Number(score).toFixed(2)}` : "Capability score not listed"}</p>
    <div className="model-meta hardware-chips">{smallestHardware(model).map((chip) => <span className="badge" key={chip}>{chip}</span>)}</div>
    <Link className="fine-print" href={`/models/${model.slug}/local`}>View hardware and model terms →</Link>
  </article>;
}

function RankingSection({ title, models, field, excludedModel }: { title: string; models: Model[]; field: BenchmarkField; excludedModel?: Model }) {
  const ordered = models.filter((model) => model.slug !== excludedModel?.slug);
  return <section className="section-wrap section ranking-section"><div className="section-heading"><div><p className="section-kicker">Published benchmark</p><h2>{title}</h2></div><p>Capability rank and score are read from the current catalogue. Model licences and local hardware requirements still apply.</p></div>
    <div className="model-grid ranked-model-grid">{ordered.map((model) => <ModelCard key={model.slug} model={model} field={field} />)}{excludedModel && <ModelCard key={excludedModel.slug} model={excludedModel} field={field} excluded />}</div>
  </section>;
}

export default function LocalOverviewPage() {
  const models = loadCatalog();
  const prices = loadHardwarePrices();
  const textTop = sortedByBenchmark(models, "jevbench").filter((model) => model.lists?.includes("jevbench-top10"));
  const imageTop = sortedByBenchmark(models, "imagejevbench").filter((model) => model.lists?.includes("imagejevbench-top10"));
  const excludedVision = imageTop.find((model) => model.slug === "vjev-vision" && model.installer_policy?.status === "excluded");
  const installable = models.filter((model) => model.installer_policy?.status === "supported" || model.installer_policy?.status === "supported_noncommercial_only");
  return <>
    <section className="section-wrap hero">
      <div className="hero-grid">
        <div><p className="eyebrow">Decision Models · Run locally</p><h1>Decision models, close to your data.</h1><p className="lede">Choose an open-weight model, check the hardware it needs, and serve it through a Jev-compatible endpoint on a machine you control.</p><div className="hero-actions"><Link className="button button-primary" href="#models">Explore local models</Link><Link className="button button-secondary" href="/hardware">Plan a hardware setup</Link></div></div>
        <aside className="hero-note"><strong>Install dm-local</strong><span>Linux and macOS:</span><div className="command-line"><code>curl -fsSL https://decisionmodels.io/local/install.sh | sh</code><CopyCommand value="curl -fsSL https://decisionmodels.io/local/install.sh | sh" /></div><span>Windows PowerShell: <code>irm https://decisionmodels.io/local/install.ps1 | iex</code></span><p className="fine-print">Then check a model with <code>dm-local plan &lt;model&gt;</code>.</p></aside>
      </div>
    </section>

    <section className="section-wrap section"><div className="benefit-grid">
      {["Your data stays on your machine", "No network round trip to the model", "One endpoint shape across local runtimes", "No telemetry; loopback by default"].map((benefit, index) => <article className="benefit" key={benefit}><span className="index">0{index + 1}</span><h3>{benefit}</h3><p>{["Prompts and decisions stay within the environment you choose.", "Measure response time on the device and network you plan to use.", "Call the same typed /v1/systemone shape used by hosted systems.", "The local service binds to 127.0.0.1 unless you change it."][index]}</p></article>)}
    </div></section>

    <RankingSection title="JevBench top 10 (text)" models={textTop} field="jevbench" />
    <RankingSection title="ImageJevBench top 10 (image)" models={imageTop} field="imagejevbench" excludedModel={excludedVision} />

    <section className="section-wrap section" id="models"><div className="section-heading"><div><p className="section-kicker">Local model catalogue</p><h2>Choose a local model</h2></div><p>{installable.filter(hasAnyExecutableInstallRecipe).length} models have an executable install recipe. Others are marked setup in preparation. Model pages show runtime, memory, and licence details.</p></div>
      {!installable.length ? <div className="callout muted"><strong>Local install recipes are being reviewed.</strong><p>Each entry will be shown as installable when its serving path and hardware requirements are recorded.</p></div> : <div className="model-grid">{installable.map((model) => {
        const suggestion = suggestedDeviceFor(model, prices);
        const licence = commercialBadge(model);
        const recipeReady = hasAnyExecutableInstallRecipe(model);
        const tested = (model.variants ?? []).some((variant) => installRecipeStatus(variant) === "tested");
        return <article className="model-card" key={model.slug}><div className="model-meta">{model.installer_policy?.status === "supported_noncommercial_only" && <span className="badge warn">Non-commercial only</span>}<span className={`badge ${recipeReady && tested ? "signal" : ""}`}>{!recipeReady ? "Setup in preparation" : tested ? "Install tested" : "Recipe ready · unverified"}</span><span className={`badge ${licence.tone}`}>{licence.label}</span>{model.modalities?.map((modality) => <span className="badge" key={modality}>{modality}</span>)}</div><h3><Link href={`/models/${model.slug}/local`}>{model.name}</Link></h3><p>{modelSummary(model)}</p><span className="fine-print">{suggestion ? `Hardware estimate: ${suggestion.name}${suggestion.install_status === "tested" ? " · install tested" : " · unverified"}` : "Hardware recommendation on request"}</span></article>;
      })}</div>}
    </section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">How it works</p><h2>Inspect before the weights arrive</h2></div><p>Installer plans use the pinned model revision and the constraints recorded for each local variant.</p></div><div className="timeline">
      {[ ["Detect", "Read CPU, GPU, memory, disk, and runtime capabilities."], ["Recommend", "Pick a compatible precision and serving runtime."], ["Download", "Fetch files from the official source and verify recorded checksums."], ["Serve", "Start a Jev-compatible API bound to loopback."], ["Self-test", "Check the endpoint before sending real requests."] ].map(([title, copy]) => <div className="timeline-item" key={title}><strong>{title}</strong>{copy}</div>)}
    </div></section>

    <section className="section-wrap section panel-grid"><article className="panel dark-panel"><p className="section-kicker">Local by default</p><h2>Control the boundary.</h2><p>Installer releases are signed, model downloads are checked against their recorded hashes, and the local API listens on loopback unless configured otherwise. No telemetry is sent.</p><div className="command-line"><code>cosign verify-blob --bundle install.sigstore.json install.sh</code><CopyCommand value="cosign verify-blob --bundle install.sigstore.json install.sh" /></div><p className="fine-print">Verify commands and release files are published alongside each installer release.</p></article><article className="panel"><p className="section-kicker">Licence, separately</p><h3>Model terms still apply.</h3><p>Using the installer does not change a model&apos;s licence. Some weights limit commercial use or redistribution.</p><div className="hero-actions"><Link className="button button-secondary" href="/local/licence">Read the installer licence</Link></div></article></section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Questions</p><h2>Before you install</h2></div></div><div className="faq">
      {[ ["Will every model run on a laptop?", "No. Each page lists the recorded memory requirements and supported platforms. Use the plan command to check the machine you intend to use."], ["Where do model files come from?", "The catalogue pins a model repository and revision. The installer uses that official source and checks recorded file hashes."], ["Does local installation include commercial rights?", "No. Model licences are separate from the installer licence; review the model's own terms before commercial use."], ["Can I use my own GPU server?", "Yes. The remote command connects to a machine you control over SSH. The remote host still needs a supported runtime and compatible hardware."] ].map(([question, answer]) => <details className="disclosure" key={question}><summary>{question}</summary><p>{answer}</p></details>)}
    </div></section>
  </>;
}
