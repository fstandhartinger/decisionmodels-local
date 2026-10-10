import Link from "next/link";
import { CopyCommand } from "@/components/copy-command";
import { CLOUD_PROVIDERS, hasKnownHardware, sourceLink, type HardwareEntry, type HwCloud } from "@/lib/hardware-all";
import { POSIX_INSTALL_COMMAND } from "@/lib/install-commands";

export const REQUEST_EMAIL = "info@decisionmodels.io";

export function installerRequestHref(slug: string) {
  return `mailto:${REQUEST_EMAIL}?subject=${encodeURIComponent(`Installer request ${slug}`)}`;
}

export function localInstallRequestHref(slug: string) {
  return `mailto:${REQUEST_EMAIL}?subject=${encodeURIComponent(`Local install request ${slug}`)}`;
}

export function OnRequestCard({ slug }: { slug: string }) {
  return <section className="section-wrap section" id="install-on-request"><div className="callout">
    <p className="section-kicker">Installer</p>
    <h2>Local install on request</h2>
    <p>This model is not in the one-command installer yet. Tell us you want it and we set it up for you, or add it to the installer.</p>
    <a className="button button-primary space-top-sm" href={localInstallRequestHref(slug)}>Local install on request</a>
  </div></section>;
}

export function LicenceBox({ installable = true }: { installable?: boolean }) {
  return <section className="section-wrap" aria-labelledby="installer-licence-title"><div className="licence-box">
    <div>
      <p className="section-kicker">Installer licence</p>
      <h2 id="installer-licence-title">Free for small teams. USD 1,000 + USD 100/month for larger companies.</h2>
      <p className="licence-line"><strong>Free for individuals and companies with up to 10 employees and up to USD 1M ARR.</strong></p>
      <p className="licence-line"><strong>Larger companies: USD 1,000 one-time + USD 100/month (self-declared).</strong> That applies above either threshold: more than 10 employees or more than USD 1 million ARR.</p>
      <p className="fine-print">This is the licence for the Decision Models <em>installer</em>. The model&apos;s own weights licence is separate and shown further down.</p>
    </div>
    <div className="licence-actions">
      <Link className="button button-primary" href="/local/licence#checkout">Buy company licence</Link>
      {installable && <Link className="button button-secondary" href="#quick-start">Free tier: just install</Link>}
      <Link className="fine-print" href="/local/licence">Read the installer terms →</Link>
    </div>
  </div></section>;
}

function gb(value?: number | null) {
  return Number.isFinite(value) ? `${value} GB` : "—";
}

export function HardwareCard({ hw }: { hw?: HardwareEntry }) {
  if (!hw || !hasKnownHardware(hw)) return <section className="section-wrap section" id="hardware-requirements"><div className="section-heading"><div><p className="section-kicker">Hardware</p><h2>Minimum and recommended hardware</h2></div></div>
    <div className="callout muted"><strong>Hardware requirements on request</strong><p>The model size is not published, so we cannot give a reliable figure yet. <a href={installerRequestHref(hw?.slug ?? "model")}>Ask us</a> and we will work it out.</p></div></section>;
  const rows = [
    ["Precision", hw.min?.precision, hw.recommended?.precision],
    ["GPU memory (VRAM)", gb(hw.min?.vram_gb), gb(hw.recommended?.vram_gb)],
    ["Example GPUs", hw.min?.gpu_examples, hw.recommended?.gpu_examples],
    ["System RAM", gb(hw.min?.ram_gb), gb(hw.recommended?.ram_gb)],
    ["Disk", gb(hw.min?.disk_gb), gb(hw.recommended?.disk_gb)]
  ];
  const cpu = hw.cpu_only;
  const apple = hw.apple_silicon;
  return <section className="section-wrap section" id="hardware-requirements">
    <div className="section-heading"><div><p className="section-kicker">Hardware</p><h2>Minimum and recommended hardware</h2></div><p>{hw.params_total_b ? `${hw.params_total_b}B parameters${hw.params_active_b && hw.params_active_b !== hw.params_total_b ? ` (${hw.params_active_b}B active)` : ""}. ` : ""}Sized for decision readouts with inputs up to about 8k tokens.</p></div>
    <div className="hw-grid">
      <article className="panel"><div className="table-wrap"><table className="hw-table"><thead><tr><th></th><th>Minimum</th><th>Recommended</th></tr></thead><tbody>{rows.map(([label, min, rec]) => <tr key={label}><th scope="row">{label}</th><td>{min || "—"}</td><td>{rec || "—"}</td></tr>)}</tbody></table></div></article>
      <article className="panel"><dl className="hw-facts">
        <div><dt>CPU only</dt><dd><span className={`badge ${cpu?.possible ? "signal" : ""}`}>{cpu?.possible ? "Yes, slowly" : "No"}</span> {cpu?.note}</dd></div>
        <div><dt>Apple Silicon</dt><dd><span className={`badge ${apple?.possible ? "signal" : ""}`}>{apple?.possible ? `Yes, ${apple.min_unified_memory_gb ?? "—"} GB+ unified memory` : "Not yet"}</span> {apple?.note}</dd></div>
      </dl></article>
    </div>
    <p className="source-note">How we computed this: weights size × bytes per value for the precision, plus 10 % and room for the context. For mixture-of-experts models all parameters must be in memory. Rounded up to common GPU sizes.{hw.source === "installer-catalog" ? " Installer figures come from the reviewed catalogue." : " These are estimates for manual setups."}</p>
  </section>;
}

function offerLine(offer?: HwCloud | null) {
  if (!offer?.instance) return null;
  return { instance: offer.instance, gpu: offer.gpu, price: Number.isFinite(offer.usd_per_hour) ? `about USD ${Number(offer.usd_per_hour).toFixed(2)}/h on demand${offer.price_region ? ` in ${offer.price_region}` : ""}` : "price on the provider page", regions: offer.eu_regions, source: sourceLink(offer.source) };
}

export function CloudGuide({ slug, hw, installer }: { slug: string; hw?: HardwareEntry; installer: boolean }) {
  const install = installer ? `dm-local install ${slug}` : null;
  const known = hasKnownHardware(hw);
  return <section className="section-wrap section" id="cloud-guide">
    <div className="section-heading"><div><p className="section-kicker">Your cloud account</p><h2>Run it on AWS, Azure or Google Cloud</h2></div><p>{installer ? "Launch a GPU machine in your own account, run the model there, and keep everything inside your cloud account and the region you pick." : "The GPU instance you would need in your own cloud account, so everything stays inside your account and the region you pick."}</p></div>
    <div className="cloud-grid">{CLOUD_PROVIDERS.map((provider) => {
      const offer = known ? offerLine(hw?.cloud?.[provider.id]) : null;
      return <article className="panel cloud-card" key={provider.id}>
        <h3>{provider.name}</h3>
        {offer ? <p className="cloud-pick"><strong>{offer.instance}</strong><br />{offer.gpu}<br />{offer.price}{offer.regions ? <><br />EU regions: {offer.regions}</> : null}{offer.source ? <> · <a href={offer.source}>price source</a></> : null}</p> : <p className="cloud-pick">Instance for this model: on request. Pick a GPU with at least {known ? gb(hw?.min?.vram_gb) : "the memory shown above"} of memory.</p>}
        {installer && <ol className="plain-steps">
          <li>Open the {provider.where} and launch a GPU instance in an EU region of your choice, using the {provider.image}.</li>
          <li>If the launch is refused, request GPU quota first: {provider.quota}.</li>
          <li>Attach {provider.private}. Do not open the model port to the internet.</li>
          <li>Connect with SSH and run the one-line installer:<div className="command-line"><code>{POSIX_INSTALL_COMMAND}</code><CopyCommand value={POSIX_INSTALL_COMMAND} /></div></li>
          {install && <li>Install the model: <div className="command-line"><code>{install}</code><CopyCommand value={install} /></div></li>}
          <li>Reach the endpoint through an SSH tunnel (<code>ssh -L 8484:127.0.0.1:8484 user@instance</code>) or from inside your private network, then call <code>http://127.0.0.1:8484/v1/systemone</code>.</li>
        </ol>}
        <p className="fine-print">Your data stays in your cloud account and region. Prices change; region, storage and traffic may add charges.</p>
      </article>;
    })}</div>
    {installer && <p className="source-note">Other options: rent a GPU from RunPod or CoreWeave, or use any machine you control over SSH: <code>dm-local remote user@host install {slug}</code>.</p>}
  </section>;
}

export function SovereigntyBox() {
  const contacts: Array<[string, string]> = [
    ["GitHub", "Installer releases and their signatures, the signature verifier (Sigstore cosign) if you do not have it, and pinned runtime binaries such as uv and llama.cpp. Recipe source code is fetched as an archive from GitHub."],
    ["Hugging Face", "The model weights, at a pinned revision, checked against recorded hashes. A token is sent only if you set one for a gated model."],
    ["Python package indexes and container registries", "Runtime packages (via uv) and container images, only for runtimes that need them, for example vLLM."],
    ["decisionmodels.io", "The installer script download. For a paid licence, it also receives your licence key when you activate and about every 30 days. The key is the only thing sent."]
  ];
  return <section className="section-wrap section" id="sovereignty"><div className="sovereign-box">
    <p className="section-kicker">Fully sovereign</p>
    <h2>Fully sovereign — your data never leaves your machines</h2>
    <p>Prompts, answers and decisions are processed on hardware you control. The installer has no telemetry: it sends no prompts, no usage data and no analytics. The local service listens on loopback (127.0.0.1) unless you change it. After setup, the model runs in Hugging Face offline mode with vendor usage statistics switched off, so serving needs no internet connection.</p>
    <h3>What the installer contacts</h3>
    <ul className="contact-list">{contacts.map(([name, copy]) => <li key={name}><strong>{name}</strong> — {copy}</li>)}</ul>
    <p className="fine-print">Setup needs these connections once; the free tier never contacts decisionmodels.io for licensing. A bundled offline package for fully isolated (air-gapped) machines is not available yet — if you need one, <a href={`mailto:${REQUEST_EMAIL}?subject=Offline%20installer`}>ask us</a>. Runtimes written by model authors remain subject to their own network behaviour.</p>
  </div></section>;
}
