import Link from "next/link";
import Image from "next/image";
import { ThemeToggle } from "@/components/theme-toggle";

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="header-inner">
        <Link href="https://decisionmodels.io" aria-label="Decision Models home" className="brand-lockup">
          <Image className="brand-light" src="/local/static/brand/dm-lockup-on-light.svg" width={190} height={27} alt="Decision Models" priority unoptimized />
          <Image className="brand-dark" src="/local/static/brand/dm-lockup-on-dark.svg" width={190} height={27} alt="Decision Models" priority unoptimized />
        </Link>
        <nav aria-label="Main navigation" className="main-nav">
          <Link href="https://decisionmodels.io/models">Models</Link>
          <Link href="/local" aria-current="page">Run locally</Link>
          <Link href="/hardware">Hardware</Link>
          <Link href="/local/licence">Licence</Link>
        </nav>
        <ThemeToggle />
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <Link className="footer-brand" href="https://decisionmodels.io">Decision Models</Link>
        <p>Run models where your work happens.</p>
        <nav aria-label="Footer navigation">
          <Link href="https://decisionmodels.io/impressum">Impressum</Link>
          <Link href="https://decisionmodels.io/privacy">Privacy</Link>
          <Link href="https://benchmarkheaven.com">Benchmarks by Benchmark Heaven</Link>
        </nav>
      </div>
    </footer>
  );
}
