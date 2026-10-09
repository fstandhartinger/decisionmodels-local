import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { runMigrations, retryAllQueuedMail } from "../lib/server-runtime.mjs";

try {
  const migrationResult = await runMigrations();
  process.stdout.write(`Database migrations ${migrationResult.skipped ? "skipped (DATABASE_URL unset)" : `complete (${migrationResult.migrations} SQL file(s))`}.\n`);
  await retryAllQueuedMail();
} catch (error) {
  process.stderr.write(`Startup preparation failed: ${String(error)}\n`);
  process.exit(1);
}

const localStandalone = path.join(process.cwd(), ".next", "standalone", "server.js");
const rootServer = path.join(process.cwd(), "server.js");
let serverEntry;
if (fs.existsSync(localStandalone)) {
  const standaloneDir = path.dirname(localStandalone);
  for (const directory of ["public", path.join(".next", "static")]) {
    const source = path.join(process.cwd(), directory);
    const destination = path.join(standaloneDir, directory);
    if (fs.existsSync(source) && !fs.existsSync(destination)) fs.cpSync(source, destination, { recursive: true });
  }
  serverEntry = localStandalone;
} else if (fs.existsSync(rootServer)) {
  serverEntry = rootServer;
} else {
  throw new Error("The standalone Next.js server entrypoint was not found.");
}
const server = spawn(process.execPath, [serverEntry], { cwd: process.cwd(), stdio: "inherit", env: process.env });
const retryTimer = setInterval(() => { retryAllQueuedMail().catch((error) => process.stderr.write(`Mail retry failed: ${String(error)}\n`)); }, 10 * 60 * 1000);
retryTimer.unref();
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => { clearInterval(retryTimer); server.kill(signal); });
server.on("exit", (code, signal) => { process.exit(signal ? 1 : (code ?? 1)); });
