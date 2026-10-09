"use client";

import { useState } from "react";
import { CopyCommand } from "@/components/copy-command";

type Tab = { id: string; title: string; steps: string[]; note?: string };
type CloudLine = { label: string; source: string; date: string; suggested?: boolean };

export function QuickStart({ slug, excluded, cloudLines, cloudMemoryGb }: { slug: string; excluded: boolean; cloudLines: CloudLine[]; cloudMemoryGb?: number }) {
  const tabs: Tab[] = [
    { id: "linux", title: "Linux & WSL2", steps: ["curl -fsSL https://decisionmodels.io/local/install.sh | sh", `dm-local install ${slug}`] },
    { id: "mac", title: "macOS", steps: ["curl -fsSL https://decisionmodels.io/local/install.sh | sh", `dm-local install ${slug}`], note: "Apple Silicon support depends on a compatible catalog variant." },
    { id: "windows", title: "Windows", steps: ["irm https://decisionmodels.io/local/install.ps1 | iex", `dm-local install ${slug}`] },
    { id: "remote", title: "Remote GPU", steps: ["curl -fsSL https://decisionmodels.io/local/install.sh | sh", `dm-local remote user@host install ${slug}`], note: "Connect to a machine you control over SSH. RunPod, CoreWeave, Lium, or your own server." },
    { id: "cloud", title: "Cloud VM", steps: ["curl -fsSL https://decisionmodels.io/local/install.sh | sh", `dm-local plan ${slug}`, `dm-local install ${slug}`], note: cloudLines.length ? `Suggested AWS, Azure, and GCP options with recorded GPU memory${cloudMemoryGb ? ` of at least ${cloudMemoryGb} GB` : ""}:` : "No sourced AWS, Azure, or GCP GPU price currently meets a reviewed GPU variant. Check region, memory, storage, and egress before choosing another instance." }
  ];
  const [active, setActive] = useState(tabs[0].id);
  const selected = tabs.find((tab) => tab.id === active) ?? tabs[0];
  if (excluded) return <div className="callout muted"><strong>Installation is not available for this entry.</strong><p>{"The catalogue does not include a reviewed local runtime variant, so we do not provide an install command."}</p></div>;
  return (
    <div className="tabs-card">
      <div className="tab-list" role="tablist" aria-label="Choose an installation platform">
        {tabs.map((tab) => <button key={tab.id} role="tab" aria-selected={active === tab.id} className={active === tab.id ? "tab active" : "tab"} onClick={() => setActive(tab.id)}>{tab.title}</button>)}
      </div>
      <div role="tabpanel" className="tab-panel">
        <ol className="step-list">
          {selected.steps.map((step, index) => <li key={`${selected.id}-${index}`}><span className="step-number">{index + 1}</span><code>{step}</code><CopyCommand value={step} /></li>)}
        </ol>
        {selected.note && <p className="fine-print">{selected.note}</p>}
        {selected.id === "cloud" && cloudLines.length > 0 && <ul className="cloud-source-list">{cloudLines.map((line) => <li key={`${line.label}-${line.source}`}>{line.suggested ? <strong>Suggested: </strong> : null}{line.label} · <a href={line.source}>Source · {line.date}</a></li>)}</ul>}
      </div>
    </div>
  );
}
