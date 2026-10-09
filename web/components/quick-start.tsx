"use client";

import { useState } from "react";
import { CopyCommand } from "@/components/copy-command";

type Tab = { id: string; title: string; steps: string[]; note?: string };
type CloudLine = { label: string; source: string; date: string };

export function QuickStart({ slug, excluded, hasRecipe, recipeTested, cloudLines, cloudMemoryGb }: { slug: string; excluded: boolean; hasRecipe: boolean; recipeTested: boolean; cloudLines: CloudLine[]; cloudMemoryGb?: number }) {
  const tabs: Tab[] = [
    { id: "linux", title: "Linux & WSL2", steps: ["curl -fsSL https://decisionmodels.io/local/install.sh | sh", `dm-local install ${slug}`] },
    { id: "mac", title: "macOS", steps: ["curl -fsSL https://decisionmodels.io/local/install.sh | sh", `dm-local install ${slug}`], note: "Apple Silicon support depends on a compatible catalog variant." },
    { id: "windows", title: "Windows", steps: ["irm https://decisionmodels.io/local/install.ps1 | iex", `dm-local install ${slug}`] },
    { id: "remote", title: "Remote GPU", steps: ["curl -fsSL https://decisionmodels.io/local/install.sh | sh", `dm-local remote user@host install ${slug}`], note: cloudLines.length ? "Connect to a machine you control over SSH. These are the lowest sourced GPU options for this model." : "Connect to a machine you control over SSH. Check its GPU memory and current price before renting." },
    { id: "cloud", title: "Cloud VM", steps: ["curl -fsSL https://decisionmodels.io/local/install.sh | sh", `dm-local plan ${slug}`, `dm-local install ${slug}`], note: cloudLines.length ? `Lowest sourced option per provider with at least ${cloudMemoryGb ?? "the model’s recommended"} GB of GPU memory:` : "No sourced RunPod, AWS, GCP, Azure, or CoreWeave price currently meets this model’s recommended GPU memory. Check provider listings before renting." }
  ];
  const [active, setActive] = useState(tabs[0].id);
  const selected = tabs.find((tab) => tab.id === active) ?? tabs[0];
  if (excluded) return <div className="callout muted"><strong>Model not offered</strong><p>This model is not offered in the installer while its licensing review is pending.</p></div>;
  if (!hasRecipe) return <div className="callout muted"><strong>Setup in preparation</strong><p>An executable install recipe is not available for this model yet.</p></div>;
  return (
    <div className="tabs-card">
      <div className="tab-list" role="tablist" aria-label="Choose an installation platform">
        {tabs.map((tab) => <button key={tab.id} role="tab" aria-selected={active === tab.id} className={active === tab.id ? "tab active" : "tab"} onClick={() => setActive(tab.id)}>{tab.title}</button>)}
      </div>
      <div role="tabpanel" className="tab-panel">
        <p className="variant-note">{recipeTested ? "An install recipe has been tested. Platform and hardware coverage is shown per variant." : "An install recipe is available, but it has not been verified by an install test."}</p>
        <ol className="step-list">
          {selected.steps.map((step, index) => <li key={`${selected.id}-${index}`}><span className="step-number">{index + 1}</span><code>{step}</code><CopyCommand value={step} /></li>)}
        </ol>
        {selected.note && <p className="fine-print">{selected.note}</p>}
        {(selected.id === "cloud" || selected.id === "remote") && cloudLines.length > 0 && <ul className="cloud-source-list">{cloudLines.map((line) => <li key={`${line.label}-${line.source}`}>{line.label} · <a href={line.source}>Price source · {line.date}</a></li>)}</ul>}
        {(selected.id === "cloud" || selected.id === "remote") && cloudLines.length > 0 && <p className="source-note">Prices change; check before renting. Region, storage, and egress may add charges.</p>}
      </div>
    </div>
  );
}
