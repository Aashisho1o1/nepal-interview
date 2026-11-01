"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", { method: "POST", json: { email, password } });
      router.push("/prepare");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Interview practice</h1>
      <p className="muted">
        Practise explaining your real study plans and funding to a fictional AI interviewer. This is
        practice only. It is not a government service and does not predict any visa decision.
      </p>
      <form className="card stack" onSubmit={submit}>
        <div>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
      <p className="muted">Milestone build: uses a synthetic student account only.</p>
    </main>
  );
}
