"use client";

import { useEffect, useState } from "react";

export function LicenceDelivery({ sessionId }: { sessionId: string }) {
  const [state, setState] = useState<"loading" | "ready" | "used" | "error">("loading");
  const [key, setKey] = useState("");
  useEffect(() => {
    let cancelled = false;
    fetch(`/local/api/licence/delivery?session_id=${encodeURIComponent(sessionId)}`, { cache: "no-store" })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) throw new Error(result.error ?? "This delivery is unavailable.");
        return result;
      })
      .then((result) => { if (!cancelled) { setKey(result.key); setState("ready"); } })
      .catch((error: unknown) => {
        if (!cancelled) setState(error instanceof Error && error.message === "already_claimed" ? "used" : "error");
      });
    return () => { cancelled = true; };
  }, [sessionId]);
  if (state === "loading") return <p role="status">Checking your licence delivery…</p>;
  if (state === "used") return <div className="callout muted"><strong>This key has already been shown.</strong><p>Check your email for the original delivery, or contact us if you cannot find it.</p></div>;
  if (state === "error") return <div className="callout muted"><strong>No one-time key is available here.</strong><p>It may have expired. Check your email for the key and contact us if you need help.</p></div>;
  return <div className="key-card"><p>Your commercial licence key</p><code>{key}</code><p>Activate it with <code>dm-local licence activate {key}</code>.</p></div>;
}
