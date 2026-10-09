import { NextResponse } from "next/server";

export function json(data: unknown, status = 200, extraHeaders?: HeadersInit) {
  const headers = new Headers(extraHeaders);
  headers.set("Cache-Control", "no-store, max-age=0");
  headers.set("Content-Type", "application/json; charset=utf-8");
  return NextResponse.json(data, { status, headers });
}

export async function readText(request: Request, limit = 16_384): Promise<string | null> {
  const length = Number(request.headers.get("content-length") || 0);
  if (length > limit) return null;
  try {
    const reader = request.body?.getReader();
    if (!reader) return "";
    const chunks: Uint8Array[] = [];
    let total = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > limit) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
    const joined = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.byteLength; }
    return new TextDecoder().decode(joined);
  } catch { return null; }
}

export async function readJson(request: Request, limit = 16_384): Promise<Record<string, unknown> | null> {
  const text = await readText(request, limit);
  if (text === null) return null;
  try {
    const value: unknown = JSON.parse(text);
    return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
  } catch { return null; }
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unexpected error.";
}
