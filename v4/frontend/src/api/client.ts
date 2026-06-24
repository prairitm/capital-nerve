export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

const API_BASE = "/api";

interface RequestOpts {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
}

/** Single HTTP entry point for the v4 frontend. No auth: the 7-step backend
 * has no users. Mirrors the v1 `api<T>()` ergonomics otherwise. */
export async function api<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const { method = "GET", body, query, signal } = opts;
  const url = new URL(API_BASE + path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }

  const res = await fetch(url.toString().replace(window.location.origin, ""), {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!res.ok) {
    const detail =
      (payload &&
        typeof payload === "object" &&
        "detail" in payload &&
        (payload as { detail: unknown }).detail) ||
      payload;
    throw new ApiError(typeof detail === "string" ? detail : res.statusText, res.status, detail);
  }
  return payload as T;
}

/** Absolute URL for binary resources (e.g. the document PDF) served by the API. */
export function apiUrl(path: string): string {
  return API_BASE + path;
}

/** Fetch a binary resource (e.g. document PDF) through the API proxy. */
export async function apiBlob(path: string, opts: { signal?: AbortSignal } = {}): Promise<Blob> {
  const url = new URL(API_BASE + path, window.location.origin);
  const res = await fetch(url.toString().replace(window.location.origin, ""), {
    method: "GET",
    signal: opts.signal,
  });

  if (!res.ok) {
    let detail: unknown = res.statusText;
    const text = await res.text();
    if (text) {
      try {
        const payload = JSON.parse(text) as { detail?: unknown };
        detail = payload.detail ?? text;
      } catch {
        detail = text;
      }
    }
    throw new ApiError(typeof detail === "string" ? detail : res.statusText, res.status, detail);
  }

  return res.blob();
}
