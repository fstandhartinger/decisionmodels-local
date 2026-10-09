import type { Metadata } from "next";
import Link from "next/link";
import { LicenceCheckoutForm } from "@/components/licence-checkout-form";

export const metadata: Metadata = { alternates: { canonical: "/local/licence" } };

export default function LicencePage() {
  return <>
    <section className="section-wrap hero"><p className="eyebrow">Local installer licence</p><h1>Simple terms for small teams.</h1><p className="lede">The free plan is for individuals and smaller companies. Larger companies can use the commercial installer licence.</p></section>
    <section className="section-wrap section split" id="pricing">
      <article className="price-card"><p className="section-kicker">Free</p><h2>Personal and smaller companies</h2><p className="price">$0 <span>to use the installer</span></p><ul><li>Individuals</li><li>Companies with up to 10 employees and under USD 1 million in annual revenue (ARR)</li><li>Use the local installer under its free terms</li></ul><p><strong>We don&apos;t check — we trust you.</strong></p><Link href="https://github.com/fstandhartinger/decisionmodels-local/releases/latest" className="button button-secondary">Read the installer terms</Link></article>
      <article className="price-card featured"><p className="section-kicker">Commercial</p><h2>For companies above either threshold</h2><p className="price">$1,000 <span>one-time setup</span></p><p className="price">$100 <span>per month</span></p><ul><li>Required when a company has more than 10 employees or at least USD 1 million ARR</li><li>One-time setup fee and monthly subscription</li><li>Cancel any time through the customer portal</li></ul><p>Prices exclude VAT where applicable. Stripe Tax is not assumed.</p></article>
      <p className="source-note full-width">Source: <a href="#pricing">Decision Models local installer licence terms</a> · checked 9 October 2026.</p>
    </section>
    <section className="section-wrap section detail-grid">
      <div><p className="section-kicker">Commercial checkout</p><h2>Start the commercial licence</h2><p className="lede">We use your declaration to place the order. No company-size verification is performed during checkout.</p><div className="panel space-top"><LicenceCheckoutForm /></div></div>
      <aside className="stack"><div className="callout"><strong>Model licences are separate.</strong><p>The installer licence does not change the rights attached to model weights. Check the model&apos;s own licence before commercial use or redistribution.</p></div><div className="panel"><h3>What you get</h3><p>After checkout, we email a one-time licence key and provide an activation command. Keep the key in your company&apos;s approved secret storage.</p><div className="command-line"><code>dm-local licence activate &lt;key&gt;</code></div></div></aside>
    </section>
    <section className="section-wrap section"><div className="section-heading"><div><p className="section-kicker">Questions</p><h2>Licence details</h2></div></div><div className="faq">
      {[ ["How do you count employees?", "Use the number of people employed by your company at the time the licence is used. If your group has several entities, include the company using the installer and its controlling group when the commercial terms require it."], ["What counts as ARR?", "Use your company's annual recurring revenue, not a one-off project invoice. The free plan applies while annual recurring revenue is under USD 1 million and the employee count is at most 10."], ["Can I cancel the monthly subscription?", "Yes. Open the Stripe customer portal from the success page or use the billing portal link attached to your account. Cancellation stops future renewals under Stripe's billing schedule."], ["Are prices tax inclusive?", "The listed prices exclude VAT where applicable. Stripe Tax is not assumed; any applicable tax is shown during checkout."], ["Does this licence clear model usage?", "No. The model's own licence controls its weights, outputs, and redistribution. Check each model page and its linked licence evidence."], ["Do you verify the company declaration?", "No. We don't check — we trust you. The commercial checkout records your company name and declaration for the licence record."] ].map(([question, answer]) => <details className="disclosure" key={question}><summary>{question}</summary><p>{answer}</p></details>)}
    </div></section>
  </>;
}
