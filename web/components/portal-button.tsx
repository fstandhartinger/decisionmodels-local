"use client";

import { useState } from "react";

export function PortalButton({ sessionId }: { sessionId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function openPortal() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/local/api/portal", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ session_id: sessionId }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "The billing portal could not be opened.");
      window.location.assign(result.url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The billing portal could not be opened.");
      setBusy(false);
    }
  }
  return <div><button className="button button-secondary" type="button" onClick={openPortal} disabled={busy}>{busy ? "Opening…" : "Manage or cancel subscription"}</button>{error && <p className="form-status error" role="alert">{error}</p>}</div>;
}
