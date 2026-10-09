# Decision Models — run locally

This Next.js app serves the Decision Models local installer and pre-installed hardware pages through the decisionmodels.io hub. It keeps its own JavaScript, CSS, fonts, public assets, APIs, and installer redirects under `/local/`; it does not configure a Next `basePath`.

## Routes

- `/local` — installer overview, supported-model lists, security notes, and FAQ.
- `/models/<slug>/local` — catalog-backed model requirements, quick start, endpoint example, and licence notes.
- `/hardware` — sourced hardware pricing, model suggestions, and the quote form.
- `/local/licence` and `/local/licence/success` — free/commercial terms, checkout, one-time key delivery, and billing portal.
- `/local/api/catalog.json`, `/local/api/health`, checkout, portal, contact, licence verification/delivery, and Stripe webhook routes.
- `/local/install.sh` and `/local/install.ps1` — HTTP 302 redirects to the latest installer release (overridable with `INSTALLER_RELEASE_BASE`).
- Static brand assets are served from `/local/static/brand/`; Next build assets use `assetPrefix: '/local'`.

## Catalog and hardware pricing

The app reads `catalog/models/*.json` and `catalog/hardware-prices.json` at build/runtime. Optional model fields default to empty or not listed. Entries without a reviewed install policy do not receive install commands. Hardware suggestions match the catalogued platform and memory requirements before comparing sourced prices. `npm run suggest:hardware` writes `catalog/hardware-suggestions.json` using same-currency medians and the documented quote formula. `npm run export:hub-cards -- <output-directory>` writes the model cards and `hardware.json` for the hub app.

The checked-in catalog files are copied from the Decision Models installer job's reviewed source catalog. Preserve each entry's source, licence evidence, and installer policy when updating the files. The public catalog endpoint strips local `recipe_source` paths from nested variants.

## Runtime configuration

See [.env.example](.env.example). `DATABASE_URL` is needed for checkout records, licence verification, and contact form storage. `LICENCE_DELIVERY_SECRET` must be at least 32 characters; it encrypts the one-time licence key and outbound mail payload until delivery. Stripe values refer to existing Stripe configuration and price IDs; the app never creates Stripe prices or products. SMTP uses the named `SMTP_*` variables. If mail is not configured, inquiries are retained in Postgres and retry on startup and every 10 minutes.

Startup executes the idempotent SQL migration in `migrations/`, retries queued mail, then starts the standalone Next server. The Docker image uses Node 22 Alpine, runs as a non-root user, and checks `GET /local/api/health`.

## Development and checks

```sh
npm install
npm run dev
npm test
npm run lint
npm run typecheck
npm run build
npm start
```

No analytics, third-party scripts, or remote fonts are loaded. Inter, Inter Tight, IBM Plex Mono, brand lockups, tokens, and the OG image are served from the local public directory.
