import type { Metadata } from "next";
import Link from "next/link";
import { CopyCommand } from "@/components/copy-command";
import { benchmarkRank, loadCatalog, sortedByBenchmark } from "@/lib/catalog";
import { dateText } from "@/lib/hardware-data";

export const metadata: Metadata = { alternates: { canonical: "/local" } };

function ModelTable({ title, models, field }: { title: string; models: ReturnType<typeof loadCatalog>; field: "jevbench" | "imagejevbench" }) {
  return (
    <div className="section">
      <div className="section-heading"><div><p className="section-kicker">Published catalogue</p><h2>{title}</h2></div><p>Rank and memory figures are shown only when the catalog includes a sourced record.</p></div>
      {!models.length ? <div className="callout muted"><strong>No published entries are available yet.</strong><p>Model pages appear here after their source, benchmark row, and local variant have been reviewed.</p></div> :
        <div className="table-wrap"><table><thead><tr><th>Rank</th><th>Model</th><th>Size</th><th>Minimum VRAM</th><th>Runs on</th></tr></thead><tbody>
          {models.map((model) => {
            const benchmark = model.benchmarks?.[field];
            const rank = benchmarkRank(benchmark);
            const vram = (model.variants ?? []).map((variant) => variant.min_vram_gb).filter((value): value is number => Number.isFinite(value));
            return <tr key={model.slug}><td className="rank">{rank !== null ? <a href={benchmark?.page ?? "https://benchmarkheaven.com/jev-models"}>#{rank}</a> : "—"}{rank !== null ? <div className="source-note"><a href={benchmark?.page ?? "https://benchmarkheaven.com/jev-models"}>{benchmark?.version ?? "Benchmark source"} · {dateText(model.sources_checked_utc)}</a></div> : null}</td><td><Link href={`/models/${model.slug}/local`}>{model.name}</Link></td><td>{model.params?.total_b ? `${model.params.total_b}B` : "—"}{model.params?.total_b && model.weights?.url ? <div className="source-note"><a href={model.weights.url}>Weights source · {dateText(model.sources_checked_utc)}</a></div> : null}</td><td>{vram.length ? `${Math.min(...vram)} GB` : "Not listed"}{vram.length ? <div className="source-note"><a href="https://decisionmodels.io/local/api/catalog.json">Variant catalog · {dateText(model.sources_checked_utc)}</a></div> : null}</td><td>{vram.length ? (model.variants ?? []).flatMap((variant) => variant.platforms ?? []).map((platform) => platform.replaceAll("-", " ")).filter((item, index, all) => all.indexOf(item) === index).join(", ") || "See model page" : "Not listed"}</td></tr>;
          })}
        </tbody></table></div>}
    </div>
  );
}

export default function LocalOverviewPage() {
  const models = loadCatalog();
  const textTop = sortedByBenchmark(models, "jevbench").filter((model) => model.lists?.includes("jevbench-top10"));
  const imageTop = sortedByBenchmark(models, "imagejevbench").filter((model) => model.lists?.includes("imagejevbench-top10"));
  const supported = models.filter((model) => model.installer_policy?.status === "supported" || model.installer_policy?.status === "supported_noncommercial_only");
  return <>
    <section className="section-wrap hero">
      <div className="hero-grid">
        <div><p className="eyebrow">Decision Models · Run locally</p><h1>Decision models, close to your data.</h1><p className="lede">Choose an open-weight model, check the hardware it needs, and serve it through a Jev-compatible endpoint on a machine you control.</p><div className="hero-actions"><Link className="button button-primary" href="#models">Explore local models</Link><Link className="button button-secondary" href="/hardware">Plan a hardware setup</Link></div></div>
        <aside className="hero-note"><strong>One local command to start</strong><span>Check the machine first. The installer recommends a catalogued variant and reports what it will download.</span><div className="command-line"><code>dm-local plan &lt;model&gt;</code><CopyCommand value="dm-local plan <model>" /></div></aside>
      </div>
    </section>

    <section className="section-wrap section"><div className="benefit-grid">
      {["Your data stays on your machine", "No network round trip to the model", "One endpoint shape across local runtimes", "No telemetry; loopback by default"].map((benefit, index) => <article className="benefit" key={benefit}><span className="index">0{index + 1}</span><h3>{benefit}</h3><p>{["Prompts and decisions stay within the environment you choose.", "Measure response time on the device and network you plan to use.", "Call the same typed /v1/systemone shape used by hosted systems.", "The local service binds to 127.0.0.1 unless you change it." ][index]}</p></article>)}
    </div></section>

    <section className="section-wrap section" id="models"><div className="section-heading"><div><p className="section-kicker">Model catalogue</p><h2>Choose a verified local variant</h2></div><p>{supported.length} entries currently include a supported local install policy. Each model page shows its source, runtime, and licence details.</p></div>
      {!supported.length ? <div className="callout muted"><strong>The first reviewed installer variants are being added.</strong><p>Entries with no verified serving recipe are not shown as installable.</p></div> : <div className="model-grid">{supported.map((model) => <article className="model-card" key={model.slug}><div className="model-meta"><span className="badge signal">{model.installer_policy?.status === "supported_noncommercial_only" ? "Non-commercial only" : "Supported"}</span>{model.modalities?.map((modality) => <span className="badge" key={modality}>{modality}</span>)}</div><h3><Link href={`/models/${model.slug}/local`}>{model.name}</Link></h3><p>{model.description ?? `${model.author ?? "Open-weight"} model · ${model.params?.total_b ? `${model.params.total_b}B parameters` : "model details on page"}`}</p><span className="fine-print">{model.variants?.length ?? 0} catalogued variant(s)</span></article>)}</div>}
    </section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">How it works</p><h2>Inspect before the weights arrive</h2></div><p>Installer plans use the pinned model revision and the constraints recorded for each local variant.</p></div><div className="timeline">
      {[ ["Detect", "Read CPU, GPU, memory, disk, and runtime capabilities."], ["Recommend", "Pick a compatible precision and serving runtime."], ["Download", "Fetch files from the official source and verify recorded checksums."], ["Serve", "Start a Jev-compatible API bound to loopback."], ["Self-test", "Check the endpoint before sending real requests." ] ].map(([title, copy]) => <div className="timeline-item" key={title}><strong>{title}</strong>{copy}</div>)}
    </div></section>

    <section className="section-wrap section panel-grid"><article className="panel dark-panel"><p className="section-kicker">Local by default</p><h2>Control the boundary.</h2><p>Installer releases are signed, model downloads are checked against their recorded hashes, and the local API listens on loopback unless configured otherwise. No telemetry is sent.</p><div className="command-line"><code>cosign verify-blob --bundle install.sigstore.json install.sh</code><CopyCommand value="cosign verify-blob --bundle install.sigstore.json install.sh" /></div><p className="fine-print">Verify commands and release files are published alongside each installer release.</p></article><article className="panel"><p className="section-kicker">Licence, separately</p><h3>Model terms still apply.</h3><p>Using the installer does not change a model&apos;s licence. Some weights limit commercial use or redistribution.</p><div className="hero-actions"><Link className="button button-secondary" href="/local/licence">Read the installer licence</Link></div></article></section>

    <section className="section-wrap" id="rankings"><ModelTable title="JevBench Capability" models={textTop} field="jevbench" /><ModelTable title="ImageJevBench Capability" models={imageTop} field="imagejevbench" /></section>

    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Questions</p><h2>Before you install</h2></div></div><div className="faq">
      {[ ["Will every model run on a laptop?", "No. Each page lists the recorded memory requirements and supported platforms. Use the plan command to check the machine you intend to use."], ["Where do model files come from?", "The catalogue pins a model repository and revision. The installer uses that official source and checks recorded file hashes."], ["Does local installation include commercial rights?", "No. Model licences are separate from the installer licence; review the model's own terms before use."], ["Can I use my own GPU server?", "Yes. The remote command connects to a machine you control over SSH. The remote host still needs a supported runtime and compatible hardware."] ].map(([question, answer]) => <details className="disclosure" key={question}><summary>{question}</summary><p>{answer}</p></details>)}
    </div></section>
  </>;
}
