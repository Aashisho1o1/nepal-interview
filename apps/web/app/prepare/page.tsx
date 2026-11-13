"use client";

// Step 2: "About you". Five quick, optional details; a full bio for a more realistic
// interview; or skip straight to practice. Everything typed here is used as given.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, ApiError, fmtMinor } from "@/lib/api";

type Details = Record<(typeof QUICK)[number][0] | (typeof BIO)[number][0], string>;
type Funding = {
  currency: string;
  required_minor: number;
  scholarships_deducted_minor: number;
  net_required_minor: number;
  identified_funds_minor: number;
  gap_minor: number;
  surplus_minor: number;
  questions: string[];
  error?: string;
};

// [key, label, hint, input mode]
const QUICK = [
  ["name", "Your name", "", "text"],
  ["home_country", "Home country", "For example, Nepal", "text"],
  ["university", "University", "The UK university that made your offer", "text"],
  ["course", "Course", "The degree you're applying for, e.g. MSc Data Science", "text"],
  ["family_income_npr", "Family's yearly income (NPR)", "In rupees, for example 1800000", "numeric"],
] as const;

const BIO = [
  ["start_month", "Course start month", "", "month"],
  ["previous_degree", "Your previous degree", "e.g. BSc CSIT, Tribhuvan University, 2024", "text"],
  ["english_test", "English test", "e.g. IELTS Academic 6.5", "text"],
  ["accommodation", "Where you'll live", "e.g. University halls, applied", "text"],
  ["tuition_gbp", "Tuition fee for year one (GBP)", "", "numeric"],
  ["living_gbp", "Living costs for year one (GBP)", "", "numeric"],
  ["scholarship_gbp", "Scholarship (GBP)", "", "numeric"],
  ["deposit_gbp", "Deposit already paid (GBP)", "", "numeric"],
  ["savings_gbp", "Family savings (GBP equivalent)", "", "numeric"],
  ["loan_gbp", "Education loan (GBP equivalent)", "", "numeric"],
] as const;

export default function AboutYou() {
  const router = useRouter();
  const [values, setValues] = useState<Details | null>(null);
  const [bioOpen, setBioOpen] = useState(false);
  const [funding, setFunding] = useState<Funding | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Details>("/profile/details")
      .then((d) => {
        setValues(d);
        if (BIO.some(([k]) => d[k])) setBioOpen(true);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.push("/");
        else setError("Could not load your details.");
      });
  }, [router]);

  const set = (k: keyof Details) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setValues((v) => (v ? { ...v, [k]: e.target.value } : v));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!values) return;
    setBusy(true);
    setError("");
    try {
      const snap = await api<{ funding: Funding }>("/profile/details", { method: "PUT", json: values });
      if (bioOpen && !snap.funding.error) {
        setFunding(snap.funding); // show the sums before moving on
        setBusy(false);
      } else {
        router.push("/interview");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Check your connection and try again.");
      setBusy(false);
    }
  }

  const field = ([key, label, hint, mode]: readonly [keyof Details, string, string, string]) => (
    <div className="field" key={key}>
      <label htmlFor={key}>{label}</label>
      <input
        id={key}
        type={mode === "month" ? "month" : "text"}
        inputMode={mode === "numeric" ? "numeric" : undefined}
        autoComplete={key === "name" ? "name" : "off"}
        placeholder={hint || undefined}
        value={values?.[key] ?? ""}
        onChange={set(key)}
      />
    </div>
  );

  return (
    <Shell
      step={2}
      width="narrow"
      title="About you"
      intro="Five quick details help your interviewer ask about your plans. The practice page says which interviewers receive them. All optional: skip any you'd rather not share."
    >
      <form onSubmit={save}>
        <div className="card">{QUICK.map(field)}</div>

        {bioOpen ? (
          <div className="card">
            <h2>Your full bio</h2>
            <p className="small">Use the figures from your offer letter and bank or loan letters.</p>
            {BIO.map(field)}
          </div>
        ) : (
          <div className="card">
            <h2>Want a more realistic interview?</h2>
            <p className="small">
              Add your full details, like funding, English test and study history, so your interviewer can ask what
              the real one would.
            </p>
            <button type="button" className="btn btn-secondary" onClick={() => setBioOpen(true)}>
              Add my full bio
            </button>
          </div>
        )}

        {funding && (
          <section className="card">
            <h2>Your funding, added up</h2>
            <table>
              <tbody>
                <tr><td>First-year costs</td><td>{fmtMinor(funding.required_minor, funding.currency)}</td></tr>
                <tr><td>Scholarships</td><td>− {fmtMinor(funding.scholarships_deducted_minor, funding.currency)}</td></tr>
                <tr><td>Amount to fund</td><td>{fmtMinor(funding.net_required_minor, funding.currency)}</td></tr>
                <tr><td>Your funds</td><td>{fmtMinor(funding.identified_funds_minor, funding.currency)}</td></tr>
                <tr>
                  <td><strong>Difference</strong></td>
                  <td className={funding.gap_minor > 0 ? "bad" : undefined}>
                    <strong>
                      {funding.gap_minor > 0
                        ? `${fmtMinor(funding.gap_minor, funding.currency)} short`
                        : funding.surplus_minor > 0
                          ? `${fmtMinor(funding.surplus_minor, funding.currency)} more than the amount to fund`
                          : "Same as the amount to fund"}
                    </strong>
                  </td>
                </tr>
              </tbody>
            </table>
            {funding.questions.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <p><strong>Be ready to explain these in your interview:</strong></p>
                <ul>{funding.questions.map((q) => <li key={q}>{q}</li>)}</ul>
              </div>
            )}
            <p className="caption">
              Added up from your figures only. A zero difference doesn&apos;t mean your funding is enough for a visa.
            </p>
          </section>
        )}

        {error && <p className="error" role="alert">{error}</p>}

        <div className="sticky-bar">
          <div className="btn-row">
            <button type="button" className="btn btn-secondary" onClick={() => router.push("/interview")}>
              Skip, try it now
            </button>
            {funding ? (
              <button type="button" className="btn btn-primary" onClick={() => router.push("/interview")}>
                Continue →
              </button>
            ) : (
              <button type="submit" className="btn btn-primary" disabled={busy || !values}>
                {busy ? "Saving…" : "Save and continue"}
              </button>
            )}
          </div>
        </div>
      </form>
    </Shell>
  );
}
