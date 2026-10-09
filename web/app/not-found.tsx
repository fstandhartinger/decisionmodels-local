import Link from "next/link";

export default function NotFound() {
  return (
    <section className="section-wrap narrow page-top">
      <p className="eyebrow">Not found</p>
      <h1>That page is not in this catalogue.</h1>
      <p className="lede">Check the address or return to the local model overview.</p>
      <Link className="button button-primary" href="/local">Browse local models</Link>
    </section>
  );
}
