import type { Metadata } from "next";
import Link from "next/link";
import { LicenceDelivery } from "@/components/licence-delivery";
import { PortalButton } from "@/components/portal-button";

export const metadata: Metadata = { alternates: { canonical: "/local/licence/success" } };

type Props = { searchParams: Promise<{ session_id?: string }> };

export default async function LicenceSuccessPage({ searchParams }: Props) {
  const { session_id: sessionId } = await searchParams;
  return <section className="section-wrap narrow page-top">
    <p className="eyebrow">Commercial installer licence</p>
    <h1>Thank you. Your licence is ready.</h1>
    <p className="lede">The key can be shown once here. A copy is queued for the email address used at checkout.</p>
    {sessionId ? <div className="stack space-top-lg"><LicenceDelivery sessionId={sessionId} /><PortalButton sessionId={sessionId} /></div> : <div className="callout muted"><strong>Checkout reference not found in this link.</strong><p>Check your email for the licence key and receipt.</p></div>}
    <p className="space-top"><Link href="/local">Return to Run locally</Link></p>
  </section>;
}
