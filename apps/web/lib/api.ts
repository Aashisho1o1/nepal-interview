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
  avatar_available: boolean;
  sessions_enabled: boolean;
};

export type Fact = {
  ref: string;
  field_name: string;
  value_json: unknown;
  source_label: string;
  source_snippet: string;
  confirmation_status: "proposed" | "confirmed" | "corrected" | "rejected";
};

export type Track = {
  id: string;
  label: string;
  stage: string;
  enabled: boolean;
  formats: { id: string; label: string; practice_seconds: number; disclosure: string }[];
  notes: string[];
};

export function fmtMinor(minor: number, currency: string) {
  return `${currency} ${(minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtSeconds(s: number) {
  const m = Math.floor(s / 60);
  const r = Math.max(0, Math.floor(s % 60));
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function describeValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v !== "object") return String(v);
  const o = v as Record<string, unknown>;
  if ("amount" in o && "currency" in o) {
    const extra = [o.period, o.available_by ? `available by ${o.available_by}` : o.kind === "loan" ? "availability date not confirmed" : null, o.already_deducted ? "already deducted from cost" : null]
      .filter(Boolean)
      .join(", ");
    return `${o.label ?? ""}: ${o.currency} ${Number(o.amount).toLocaleString("en-US")}${extra ? ` (${extra})` : ""}`;
  }
  if ("annual_amount" in o) return `Sponsor income (${o.earner}): ${o.currency} ${Number(o.annual_amount).toLocaleString("en-US")} per year`;
  return JSON.stringify(o);
}
