// Device tiers for /hardware. Every number here is sourced (see `sources`) or marked as an estimate.
// Research notes and the full device table: ~/jobs/dm-hardware-page-20261012 (RESULT.md, research/*.md), 12 Oct 2026.

export type Offer = "preinstall" | "byo" | "not-yet";

export type Fit = { level: "measured" | "fits" | "estimate" | "no"; text: string };

export type TierDevice = {
  id: string;
  name: string;
  examples?: string;
  memory: string;
  fits: { s1pro: Fit; moe: Fit; quyet: Fit; small: Fit };
  power: string;
  noise: string;
  price: string;
  offer: Offer;
  offerNote: string;
  sources: string[];
};

export type Tier = { id: string; title: string; kicker: string; summary: string; devices: TierDevice[] };

export const MODEL_COLUMNS = [
  { key: "s1pro", title: "s1-pro class", detail: "26B dense: Perplexity Decider v1.1, vLLM-SR d3" },
  { key: "moe", title: "26B-A4B MoE", detail: "Blink v0.3 (s1-fast), Surogate Rune" },
  { key: "quyet", title: "Quyet-1.0-Large", detail: "31B dense" },
  { key: "small", title: "4B models", detail: "e.g. H2O-Lightning-4B, NeoHorse Jev 4B" }
] as const;

const NOT_SUPPORTED_S1PRO: Fit = { level: "no", text: "Not yet: needs the REAX Engine (NVIDIA CUDA)" };

export const TIERS: Tier[] = [
  {
    id: "edge",
    title: "Edge",
    kicker: "Tier 1",
    summary: "Small, low-power boards next to a machine, a camera or a robot. Good for 4B models; the 128 GB Thor also holds the larger MoE models.",
    devices: [
      {
        id: "jetson-orin-nano-super",
        name: "NVIDIA Jetson Orin Nano Super Developer Kit",
        memory: "8 GB",
        fits: {
          s1pro: { level: "no", text: "Does not fit" },
          moe: { level: "no", text: "Does not fit" },
          quyet: { level: "no", text: "Does not fit" },
          small: { level: "estimate", text: "4-bit / 8-bit · ≈1–3 dec/s (estimate)" }
        },
        power: "7–25 W",
        noise: "Small fan; no dB figure published",
        price: "€559 (Voelkner) · $399",
        offer: "byo",
        offerNote: "Bring your own board; our installer and setup guide. Not yet tested by us.",
        sources: ["jetson-nano-price", "jetson-price-rise", "jetson-specs"]
      },
      {
        id: "jetson-agx-thor",
        name: "NVIDIA Jetson AGX Thor Developer Kit",
        examples: "Jetson AGX Orin 64 GB ($3,499) is the smaller option for 4B and 8-bit MoE models.",
        memory: "128 GB unified",
        fits: {
          s1pro: NOT_SUPPORTED_S1PRO,
          moe: { level: "estimate", text: "BF16 · ≈7–13 dec/s (estimate)" },
          quyet: { level: "fits", text: "BF16 fits in memory · speed not estimated" },
          small: { level: "estimate", text: "BF16 · ≈15–25 dec/s (estimate)" }
        },
        power: "40–130 W module",
        noise: "Active cooling; no dB figure published",
        price: "€8,010 (Generation Robots) · $5,499",
        offer: "byo",
        offerNote: "Bring your own kit; our installer and setup guide. Not yet tested by us.",
        sources: ["thor-price-eu", "jetson-price-rise", "thor-specs", "spark-thor-bench"]
      }
    ]
  },
  {
    id: "desk",
    title: "Desk",
    kicker: "Tier 2",
    summary: "Quiet boxes that sit on a desk or in a small office rack. The 128 GB GB10 systems hold every model in this lineup at full precision.",
    devices: [
      {
        id: "gb10",
        name: "NVIDIA GB10 systems (DGX Spark class)",
        examples: "ASUS Ascent GX10, Gigabyte AI TOP ATOM, Dell Pro Max with GB10, Lenovo ThinkStation PGX, HP ZGX Nano, NVIDIA DGX Spark",
        memory: "128 GB unified",
        fits: {
          s1pro: { level: "estimate", text: "FP8 on REAX Engine · ≈2–4 dec/s (estimate, untested on GB10)" },
          moe: { level: "estimate", text: "BF16 / NVFP4 · ≈15–25 dec/s (estimate)" },
          quyet: { level: "estimate", text: "NVFP4 · ≈5–10 dec/s (estimate)" },
          small: { level: "estimate", text: "BF16 · ≈30–50 dec/s (estimate)" }
        },
        power: "240 W power supply",
        noise: "Quiet desktop box (NVIDIA lists about 29 dB under load)",
        price: "€6,468–6,491 in stock (Alternate, 12 Oct) · DGX Spark $6,950",
        offer: "preinstall",
        offerNote: "Pre-installed by us on request, on the partner-brand boxes (ASUS, Gigabyte, Dell, Lenovo, HP).",
        sources: ["gb10-alternate", "spark-price", "spark-specs", "lmsys-spark", "spark-thor-bench"]
      },
      {
        id: "mac-mini",
        name: "Apple Mac mini with M5 Pro, 64 GB",
        memory: "64 GB unified",
        fits: {
          s1pro: NOT_SUPPORTED_S1PRO,
          moe: { level: "estimate", text: "8-bit · ≈5–8 dec/s (estimate)" },
          quyet: { level: "fits", text: "8-bit fits in memory · speed not estimated" },
          small: { level: "fits", text: "BF16 fits · speed not estimated" }
        },
        power: "6 W idle · 145 W max",
        noise: "Near silent at idle; no dB figure published",
        price: "from €3,099 · $2,699 (Apple list price at launch)",
        offer: "preinstall",
        offerNote: "Set up by us on request: macOS stays untouched, our software is added as separate apps.",
        sources: ["apple-mini-price", "apple-mini-specs", "apple-power-mini", "llamacpp-apple"]
      },
      {
        id: "strix-halo",
        name: "AMD Ryzen AI Max+ 395 mini-PCs, 128 GB",
        examples: "Framework Desktop, HP Z2 Mini G1a, GMKtec EVO-X2",
        memory: "128 GB unified",
        fits: {
          s1pro: NOT_SUPPORTED_S1PRO,
          moe: { level: "fits", text: "Fits in memory; GPU support in our installer is not ready yet" },
          quyet: { level: "fits", text: "Fits in memory; GPU support not ready yet" },
          small: { level: "fits", text: "Fits; CPU recipes only today" }
        },
        power: "About 120–145 W under AI load (reviews of similar boxes)",
        noise: "About 43–45 dBA under load (reviews of similar boxes)",
        price: "€3,889 (Framework, DE) – €6,084 (HP at Bechtle)",
        offer: "not-yet",
        offerNote: "Listed for comparison. We will add it once our installer supports AMD GPUs.",
        sources: ["framework-de", "hp-z2-bechtle", "sth-strix", "hh-strix"]
      }
    ]
  },
  {
    id: "workstation",
    title: "Workstation",
    kicker: "Tier 3",
    summary: "A tower under the desk or a large Mac. This is where we have our own measurements: the RTX PRO 6000 runs every model in the lineup on one card.",
    devices: [
      {
        id: "rtx-pro-6000",
        name: "Workstation with NVIDIA RTX PRO 6000 Blackwell",
        memory: "96 GB GPU memory",
        fits: {
          s1pro: { level: "measured", text: "FP8 on REAX Engine · 15.7 dec/s (measured)" },
          moe: { level: "measured", text: "Blink NVFP4 · 97 dec/s · Rune BF16 · 76 dec/s (measured)" },
          quyet: { level: "measured", text: "NVFP4 · 36.7 dec/s (measured)" },
          small: { level: "measured", text: "Plumb-4B BF16 · about 200 dec/s (measured, short prompts)" }
        },
        power: "GPU 600 W (300 W Max-Q edition)",
        noise: "Workstation fan noise under load",
        price: "GPU card €17,850–20,091 (Alternate, 12 Oct) plus the base system",
        offer: "preinstall",
        offerNote: "Pre-installed by us on request, as a complete workstation from an established system builder.",
        sources: ["own-reax", "own-lineup", "pro6000-alternate"]
      },
      {
        id: "rtx-5090",
        name: "Workstation with NVIDIA GeForce RTX 5090",
        memory: "32 GB GPU memory",
        fits: {
          s1pro: { level: "measured", text: "FP8 on REAX Engine · 10.3 dec/s (measured)" },
          moe: { level: "estimate", text: "Blink NVFP4 · ≈60–80 dec/s (estimate); Rune BF16 does not fit" },
          quyet: { level: "estimate", text: "NVFP4 · ≈25–30 dec/s (estimate)" },
          small: { level: "estimate", text: "BF16 · ≈140–170 dec/s (estimate)" }
        },
        power: "GPU 575 W",
        noise: "Gaming-PC class; louder than a Mac Studio",
        price: "GPU card €4,850–7,300 (Germany, Sep–Oct) plus the base system",
        offer: "preinstall",
        offerNote: "Pre-installed by us on request, as a complete workstation from an established system builder.",
        sources: ["own-hwsweep", "rtx5090-pcgh", "rtx5090-alternate", "lmsys-spark"]
      },
      {
        id: "mac-studio",
        name: "Apple Mac Studio with M5 Max or M5 Ultra",
        examples: "M5 Max up to 128 GB; M5 Ultra 96 or 256 GB (512 GB announced for late October)",
        memory: "96–256 GB unified (M5 Ultra)",
        fits: {
          s1pro: NOT_SUPPORTED_S1PRO,
          moe: { level: "estimate", text: "BF16 · M5 Ultra ≈15–25, M5 Max ≈10–16 dec/s (estimate)" },
          quyet: { level: "fits", text: "BF16 fits (96 GB and up) · speed not estimated" },
          small: { level: "fits", text: "BF16 fits · speed not estimated" }
        },
        power: "M5 Max 7 W idle · 200 W max; M5 Ultra 9 W idle · 385 W max",
        noise: "Very quiet; fan audible only under sustained load (reviews)",
        price: "M5 Ultra from €6,599 · $5,499 (Apple list price at launch)",
        offer: "preinstall",
        offerNote: "Set up by us on request: macOS stays untouched, our software is added as separate apps.",
        sources: ["apple-studio-price", "apple-studio-specs", "apple-power-studio", "macstories-m5ultra", "llamacpp-apple"]
      }
    ]
  },
  {
    id: "rack",
    title: "Rack",
    kicker: "Tier 4",
    summary: "Several GPUs in one chassis for high volume. Each GPU runs its own copy of a model, so throughput grows with the number of GPUs.",
    devices: [
      {
        id: "tinybox",
        name: "tiny corp tinybox",
        examples: "New tinybox with 1–2 RTX PRO 6000 (from $7,000 without GPUs, +$19,000 per GPU); tinybox pro v2 with 8× RTX 5090 ($100,000) or 8× RTX PRO 6000 ($200,000)",
        memory: "96–768 GB GPU memory",
        fits: {
          s1pro: { level: "estimate", text: "About the single-GPU figure × number of GPUs (estimate)" },
          moe: { level: "estimate", text: "About the single-GPU figure × number of GPUs (estimate)" },
          quyet: { level: "estimate", text: "About the single-GPU figure × number of GPUs (estimate)" },
          small: { level: "estimate", text: "About the single-GPU figure × number of GPUs (estimate)" }
        },
        power: "1,700 W supply (tinybox); 4 × 2,000 W (pro v2)",
        noise: "Under 50 dB (tinybox); pro v2 is a 5U rack server",
        price: "$7,000–200,000, sold in USD only; import VAT and duty extra",
        offer: "byo",
        offerNote: "Order directly from tiny corp; we install our software remotely over SSH.",
        sources: ["tinybox-shop", "tinybox-faq"]
      }
    ]
  }
];

export const SOURCES: Record<string, { label: string; url: string; date: string }> = {
  "own-reax": { label: "Our REAX Engine measurement, Perplexity Decider v1.1, RTX PRO 6000", url: "", date: "10 Oct 2026" },
  "own-lineup": { label: "Our serving measurements on RTX PRO 6000 (Blink, Rune, Quyet, Plumb-4B)", url: "", date: "3–11 Oct 2026" },
  "own-hwsweep": { label: "Our REAX Engine hardware sweep (RTX 5090, RTX PRO 6000, H100, H200, B200)", url: "", date: "10 Oct 2026" },
  "jetson-nano-price": { label: "Voelkner: Jetson Orin Nano Super Developer Kit", url: "https://www.voelkner.de/products/8761803/Nvidia-Super-Developer-Kit-Jetson-Orin-Nano-8GB-6-x-1.7GHz.html", date: "12 Oct 2026" },
  "jetson-price-rise": { label: "Hardware Busters: Jetson price increase", url: "https://hwbusters.com/news/nvidia-jetson-prices-jump-up-to-101-the-249-orin-nano-super-is-now-399/", date: "21 Jul 2026" },
  "jetson-specs": { label: "NVIDIA Jetson Orin specifications", url: "https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/", date: "12 Oct 2026" },
  "thor-price-eu": { label: "Generation Robots: Jetson AGX Thor Developer Kit", url: "https://www.generationrobots.com/en/404410-nvidia-jetson-agx-thor-developer-kit.html", date: "12 Oct 2026" },
  "thor-specs": { label: "NVIDIA Jetson Thor specifications", url: "https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-thor/", date: "12 Oct 2026" },
  "spark-thor-bench": { label: "JetsonHacks: DGX Spark vs Jetson Thor llama.cpp benchmarks", url: "https://jetsonhacks.com/wp-content/uploads/2025/10/SparkThorLlamaBenchmarks.html", date: "31 Oct 2025" },
  "gb10-alternate": { label: "Alternate.de: GB10 systems", url: "https://www.alternate.de/html/search.html?query=GB10", date: "12 Oct 2026" },
  "spark-price": { label: "ServeTheHome: DGX Spark 64 GB launched, 128 GB price increase", url: "https://www.servethehome.com/nvidia-dgx-spark-64gb-launched-and-big-128gb-gb10-price-increases/", date: "3 Oct 2026" },
  "spark-specs": { label: "NVIDIA DGX Spark support and specifications", url: "https://www.nvidia.com/en-eu/support/dgx-spark/", date: "12 Oct 2026" },
  "lmsys-spark": { label: "LMSYS: NVIDIA DGX Spark in-depth review (prompt-processing comparison)", url: "https://lmsys.org/blog/2025-10-13-nvidia-dgx-spark/", date: "13 Oct 2025" },
  "apple-mini-price": { label: "ChannelPartner: Mac mini M6 and M5 Pro prices", url: "https://www.channelpartner.de/article/4214044/neuer-mac-mini-m6-kommt-mit-kraftigem-preisaufschlag.html", date: "26 Aug 2026" },
  "apple-mini-specs": { label: "Apple: Mac mini technical specifications", url: "https://www.apple.com/de/mac-mini/specs/", date: "12 Oct 2026" },
  "apple-power-mini": { label: "Apple: Mac mini power consumption and thermal output", url: "https://support.apple.com/103253", date: "12 Oct 2026" },
  "apple-studio-price": { label: "Macwelt: Mac Studio M5 Max and M5 Ultra prices", url: "https://www.macwelt.de/article/3220005/mac-studio-m5-max-m5-ultra.html", date: "25 Aug 2026" },
  "apple-studio-specs": { label: "Apple: Mac Studio technical specifications", url: "https://www.apple.com/de/mac-studio/specs/", date: "12 Oct 2026" },
  "apple-power-studio": { label: "Apple: Mac Studio power consumption and thermal output", url: "https://support.apple.com/en-asia/102027", date: "12 Oct 2026" },
  "macstories-m5ultra": { label: "MacStories: M5 Ultra Mac Studio review (prompt processing)", url: "https://www.macstories.net/stories/m5-ultra-mac-studio-review-the-dream-mac-for-local-ai-agents/", date: "Sep 2026" },
  "llamacpp-apple": { label: "llama.cpp: Apple Silicon performance table", url: "https://github.com/ggml-org/llama.cpp/discussions/4167", date: "12 Oct 2026" },
  "framework-de": { label: "Framework Desktop configurator (DE)", url: "https://frame.work/de/en/products/desktop-diy-amd-aimax300/configuration/new", date: "12 Oct 2026" },
  "hp-z2-bechtle": { label: "Bechtle: HP Z2 Mini G1a", url: "https://www.bechtle.com/de-en/shop/product-family/hp-z2-mini-g1a-workstation--6634--f", date: "12 Oct 2026" },
  "sth-strix": { label: "ServeTheHome: Minisforum MS-S1 Max review (power, noise)", url: "https://www.servethehome.com/minisforum-ms-s1-max-review-the-best-ryzen-ai-max-mini-pc-yet/4/", date: "14 Jan 2026" },
  "hh-strix": { label: "HotHardware: AMD Ryzen AI Halo review (power, noise)", url: "https://hothardware.com/reviews/amd-ryzen-ai-halo-hands-on-review?page=4", date: "6 Jul 2026" },
  "pro6000-alternate": { label: "Alternate.de: RTX PRO 6000", url: "https://www.alternate.de/html/search.html?query=RTX+PRO+6000", date: "12 Oct 2026" },
  "rtx5090-pcgh": { label: "PC Games Hardware: RTX 5090 prices", url: "https://www.pcgameshardware.de/Geforce-RTX-5090-Grafikkarte-281029/News/Preis-5099-US-Dollar-Meme-Realitaet-1552572/", date: "1 Sep 2026" },
  "rtx5090-alternate": { label: "Alternate.de: RTX 5090", url: "https://www.alternate.de/html/search.html?query=RTX+5090", date: "12 Oct 2026" },
  "tinybox-shop": { label: "tiny corp: tinybox shop and configurator", url: "https://tinygrad.org/", date: "12 Oct 2026" },
  "tinybox-faq": { label: "tiny corp: FAQ (ordering, shipping, payment)", url: "https://tinygrad.org/faq.html", date: "12 Oct 2026" }
};

export const OFFER_LABEL: Record<Offer, string> = {
  preinstall: "Pre-installed by us, on request",
  byo: "Bring your own device",
  "not-yet": "Not supported yet"
};
