const TOKEN_KEY = "cn_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

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

export async function api<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const { method = "GET", body, query, signal } = opts;
  const url = new URL(API_BASE + path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url.toString().replace(window.location.origin, ""), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  if (res.status === 401) {
    setToken(null);
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
    throw new ApiError("Unauthorized", 401, null);
  }

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
      (payload && typeof payload === "object" && "detail" in payload && (payload as { detail: unknown }).detail) ||
      payload;
    throw new ApiError(typeof detail === "string" ? detail : res.statusText, res.status, detail);
  }
  return payload as T;
}

/** Fetch a binary resource (e.g. uploaded PDF) with the same auth semantics as `api()`. */
export async function apiBlob(path: string, opts: { signal?: AbortSignal } = {}): Promise<Blob> {
  const url = new URL(API_BASE + path, window.location.origin);
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url.toString().replace(window.location.origin, ""), {
    method: "GET",
    headers,
    signal: opts.signal,
  });

  if (res.status === 401) {
    setToken(null);
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
    throw new ApiError("Unauthorized", 401, null);
  }

  if (!res.ok) {
    let detail: unknown = res.statusText;
    const text = await res.text();
    if (text) {
      try {
        const payload = JSON.parse(text);
        detail =
          payload && typeof payload === "object" && "detail" in payload
            ? (payload as { detail: unknown }).detail
            : payload;
      } catch {
        detail = text;
      }
    }
    throw new ApiError(typeof detail === "string" ? detail : res.statusText, res.status, detail);
  }

  return res.blob();
}

/**
 * Upload a file via multipart/form-data and return the parsed JSON response.
 * Used by the admin ingestion page — uses the same auth + error semantics as
 * the JSON `api()` client so callers don't need to know about FormData quirks.
 */
export async function apiUpload<T>(
  path: string,
  formData: FormData,
  opts: { signal?: AbortSignal } = {},
): Promise<T> {
  const url = API_BASE + path;
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: formData,
    signal: opts.signal,
  });

  if (res.status === 401) {
    setToken(null);
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
    throw new ApiError("Unauthorized", 401, null);
  }

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
      (payload && typeof payload === "object" && "detail" in payload && (payload as { detail: unknown }).detail) ||
      payload;
    throw new ApiError(
      typeof detail === "string" ? detail : res.statusText,
      res.status,
      detail,
    );
  }
  return payload as T;
}
