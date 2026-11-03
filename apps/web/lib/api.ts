// Thin client for the session API (same-origin via the Next.js rewrite).

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public body: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...rest,
    headers: { ...(json !== undefined ? { "content-type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    throw new ApiError(res.status, body.error ?? String(res.status), body.message ?? detail ?? `Request failed (${res.status})`, body);
  }
  return body as T;
}

export type Balance = { granted: number; consumed: number; reserved: number; available: number };
export type Me = {
  email: string;
  display_name: string;
  is_synthetic: boolean;
  balances: { premium_seconds: Balance; basic_seconds: Balance };
  video_available: boolean;
  voice_available: boolean;
};

export type Fact = {
  ref: string;
  field_name: string;
  value_json: unknown;
  source_label: string;
  source_snippet: string;
  confirmation_status: "proposed" | "confirmed" | "corrected" | "rejected";
};

export function fmtMinor(minor: number, currency: string) {
  return `${currency} ${(minor / 100).toLocaleString("en-GB", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

export const firstName = (me: Me | null) => me?.display_name.split(" ")[0] ?? "";

export type SessionSummary = {
  id: string;
  mode: "avatar" | "voice";
  status: string;
  created_at: string;
  end_reason: string | null;
};

export function fmtSeconds(s: number) {
  const m = Math.floor(s / 60);
  const r = Math.max(0, Math.floor(s % 60));
  return `${m}:${r.toString().padStart(2, "0")}`;
}
