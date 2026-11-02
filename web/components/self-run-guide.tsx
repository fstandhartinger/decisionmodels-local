import Link from "next/link";
import { ContactForm } from "./contact-form";
import { CopyCommand } from "./copy-command";
import { CloudGuide, LicenceBox } from "./local-sections";
import { selfRunModel, licenceCopy, publicRepoId, localRequestCurl } from "@/lib/self-run";
import type { HardwareEntry } from "@/lib/hardware-all";

export function SelfRunGuide({ slug, name, known, hw }: { slug: string; name: string; known: boolean; hw?: HardwareEntry }) {
  const facts = selfRunModel(slug);
  const repo = facts?.hf_repo ?? hw?.hf_repo;
  const url = repo ? `https://huggingface.co/${repo}` : undefined;
  const memory = facts?.vram_gb; // Use served precision, never a smaller hypothetical quantisation.
  const cloudHw: HardwareEntry = { slug, name, min: memory ? { vram_gb: memory } : null };
  return <div className="self-run-guide">
    <section className="section-wrap hero">
      <p className="eyebrow"><Link href="/local">Run locally</Link> / Public weights</p>
      <h1>Run {name} yourself</h1>
      <p className="lede space-top-sm">{licenceCopy(facts?.licence)}</p>
      <p>This model has no supported dm-local installer recipe. Use the public weights directly where the runtime supports them.</p>
      {!known && <div className="callout"><strong>Unverified model reference</strong><p>This page does not confirm that the model or its weights are available. Check the spelling and the original model card.</p></div>}
      <dl className="hw-facts space-top">
        <div><dt>Weights</dt><dd>{url ? <a href={url}>{repo}</a> : "Repository not listed"}</dd></div>
        <div><dt>Pinned revision</dt><dd>{facts?.revision && url ? <a href={`${url}/tree/${facts.revision}`}>{facts.revision}</a> : "Not verified yet"}</dd></div>
        <div><dt>Parameters</dt><dd>{facts?.params ?? (hw?.params_total_b ? `${hw.params_total_b}B` : "Unknown")}</dd></div>
        <div><dt>GPU memory needed</dt><dd>{memory ? `${memory} GB estimated for the served precision and 8k context` : "Unknown for this runtime and precision"}</dd></div>
        <div><dt>Precision</dt><dd>{facts?.precision ?? "Not verified"}</dd></div>
        <div><dt>Model licence</dt><dd>{facts?.licence ?? "Not listed; check the model card"}</dd></div>
      </dl>
      <div className="hero-actions"><a className="button button-primary" href="#run-weights">Run the public weights</a><Link className="button button-secondary" href={`/local/cloud?model=${encodeURIComponent(slug)}`}>Cloud quick guides</Link></div>
    </section>
    <section className="section-wrap section" id="run-weights"><div className="panel">
      <p className="section-kicker">Your machine</p><h2>Serve the weights</h2>
      {facts?.command ? <><p>Use Linux with an NVIDIA GPU and a compatible CUDA driver. These commands have not been run by us end-to-end. Check the model card for runtime versions and any custom readout code.</p>
        <pre className="code-block">{`python3 -m venv .venv\n. .venv/bin/activate\npython -m pip install vllm\n${facts.command}`}</pre><CopyCommand value={`python3 -m venv .venv\n. .venv/bin/activate\npython -m pip install vllm\n${facts.command}`} />
        <p className="fine-print">The server listens on localhost port 8000. This is the stock vLLM API; a Jev-compatible endpoint may need the model author’s readout code. No runtime compatibility or performance test is implied.</p>
        {repo && <><h3 className="space-top">Send a request to your local server</h3><p>With the server running, this OpenAI-compatible chat completion request goes to localhost:8000. We have not tested this request.</p>
          <pre className="code-block">{localRequestCurl(repo)}</pre><CopyCommand value={localRequestCurl(repo)} /></>}</> : <p>{facts?.missing ?? "A verified full checkpoint, pinned revision and compatible runtime are not recorded yet. Check the model card before choosing a serving command."}{facts?.gated && " Request access on Hugging Face first and accept the author’s terms."}{facts?.adapter_base && (publicRepoId(facts.adapter_base) ? ` This is an adapter; obtain the base model (${publicRepoId(facts.adapter_base)}) and follow the author’s adapter instructions.` : " This is an adapter; obtain its base model from the model card and follow the author’s adapter instructions.")}</p>}
      {url && <p><a href={url}>Read the model card →</a></p>}
    </div></section>
    <CloudGuide slug={slug} hw={cloudHw} installer={false} />
    <section className="section-wrap section"><div className="callout"><h2>Public weights need no Decision Models licence</h2><p>Running the public weights yourself with vLLM needs no Decision Models licence. The model’s own licence still applies. The dm-local installer provides one-command installation, a self-test and a Jev-compatible endpoint for supported models. This model has no supported installer recipe; buying a licence does not add support.</p></div></section>
    <LicenceBox installable={false} />
    <section className="section-wrap section" id="local-request"><details className="disclosure"><summary>Need help setting it up?</summary><p>Share your hardware and use case. We review feasibility before offering setup help.</p><ContactForm mode="local" models={[{ slug, name }]} selectedModel={slug} /></details></section>
  </div>;
}
