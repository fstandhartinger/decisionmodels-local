import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ModelLocalPage from "../app/models/[slug]/local/page";
import LocalOverviewPage from "../app/local/page";
import { benchmarkRank, loadCatalog } from "../lib/catalog";
import { DECISION_INDEX_NOT_MEASURED, decisionIndexText, loadDecisionIndex } from "../lib/decision-index";

const snapshot = loadDecisionIndex();
const decisionIndexMention = /on the Decision Index \(|Decision Index: not yet measured/;

describe("Decision Index next to every JevBench rank", () => {
  it("ships a versioned snapshot with its source", () => {
    expect(snapshot.version).toMatch(/^\d+\.\d+/);
    expect(snapshot.data_source).toContain("index.json");
    expect(Object.keys(snapshot.models).length).toBeGreaterThan(0);
  });

  it("formats a measured and an unmeasured model", () => {
    const [slug, entry] = Object.entries(snapshot.models)[0];
    expect(decisionIndexText(slug, snapshot)).toMatch(new RegExp(`^#${entry.rank} on the Decision Index \\(${snapshot.version.replace(/\./g, "\\.")}, \\d{1,2} \\w+ \\d{4}\\)$`));
  });

  it("says not yet measured when a model has no Decision Index result", () => {
    expect(decisionIndexText("no-such-model", snapshot)).toBe(DECISION_INDEX_NOT_MEASURED);
  });

  it("never renders a JevBench or ImageJevBench rank on a model page without a Decision Index mention", async () => {
    const ranked = loadCatalog().filter((model) => model.installer_policy?.status !== "excluded" && [model.benchmarks?.jevbench, model.benchmarks?.imagejevbench].some((item) => benchmarkRank(item) !== null));
    expect(ranked.length).toBeGreaterThan(0);
    let checked = 0;
    for (const model of ranked) {
      const html = renderToStaticMarkup(await ModelLocalPage({ params: Promise.resolve({ slug: model.slug }) }));
      if (!/#\d+ on (?:Image)?JevBench/.test(html)) continue;
      checked += 1;
      expect(html, model.slug).toMatch(decisionIndexMention);
    }
    expect(checked).toBeGreaterThan(0);
  }, 60_000);

  it("renders the Decision Index for every ranked card on /local", () => {
    const html = renderToStaticMarkup(LocalOverviewPage());
    const cards = html.split('<article class="model-card ranked-model-card').slice(1);
    expect(cards.length).toBeGreaterThan(0);
    for (const card of cards) expect(card.split("</article>")[0]).toMatch(decisionIndexMention);
  });

  it("cites the measured rank for a known model and not-measured for another", async () => {
    const html = renderToStaticMarkup(await ModelLocalPage({ params: Promise.resolve({ slug: "winnow-12b" }) }));
    expect(html).toContain(`#${snapshot.models["winnow-12b"].rank} on the Decision Index (${snapshot.version}`);
    const other = renderToStaticMarkup(await ModelLocalPage({ params: Promise.resolve({ slug: "decider-12b" }) }));
    expect(other).toContain(DECISION_INDEX_NOT_MEASURED);
  });
});
