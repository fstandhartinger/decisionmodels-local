"use client";

import { useEffect, useState } from "react";

export function LicenceDelivery({ sessionId }: { sessionId: string }) {
  const [state, setState] = useState<"loading" | "ready" | "used" | "pending" | "error">("loading");
  const [key, setKey] = useState("");
  useEffect(() => {
    let cancelled = false;
    async function pollDelivery() {
      for (let attempt = 0; attempt < 15 && !cancelled; attempt += 1) {
        try {
          const response = await fetch(`/local/api/licence/delivery?session_id=${encodeURIComponent(sessionId)}`, { cache: "no-store" });
          const result = await response.json();
          if (response.status === 202 && result.pending) {
            if (attempt === 14) { setState("pending"); return; }
            await new Promise((resolve) => setTimeout(resolve, 2_000));
            continue;
          }
          if (!response.ok) throw new Error(result.error ?? "This delivery is unavailable.");
          setKey(result.key);
          setState("ready");
          return;
        } catch (error) {
          if (!cancelled) setState(error instanceof Error && error.message === "already_claimed" ? "used" : "error");
          return;
        }
      }
    }
    void pollDelivery();
    return () => { cancelled = true; };
  }, [sessionId]);
  if (state === "loading") return <p role="status">Checking your licence delivery…</p>;
  if (state === "used") return <div className="callout muted"><strong>This key has already been shown.</strong><p>Check your email for the original delivery, or contact us if you cannot find it.</p></div>;
  if (state === "pending") return <div className="callout muted"><strong>Payment is still processing.</strong><p>A licence key is provided after payment clears. Check back shortly or look for the delivery email.</p></div>;
  if (state === "error") return <div className="callout muted"><strong>No one-time key is available here.</strong><p>It may have expired. Check your email for the key and contact us if you need help.</p></div>;
  return <div className="key-card"><p>Your commercial licence key</p><code>{key}</code><p>Activate it with <code>dm-local licence activate {key}</code>.</p></div>;
}
