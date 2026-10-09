const defaultBase = "https://github.com/fstandhartinger/decisionmodels-local/releases/latest/download";

export async function GET() {
  const base = (process.env.INSTALLER_RELEASE_BASE || defaultBase).replace(/\/+$/, "");
  return new Response(null, { status: 302, headers: { Location: `${base}/install.ps1`, "Cache-Control": "public, max-age=300" } });
}

export async function HEAD() { return GET(); }
