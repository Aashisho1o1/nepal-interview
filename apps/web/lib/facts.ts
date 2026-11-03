// Human labels for facts. Raw field keys and ISO dates never reach the screen.

import type { Fact } from "./api";

export const GROUPS: [string, string[]][] = [
  ["About you", ["student.full_name", "academic.history", "academic.gap_explanation", "academic.english_test"]],
  ["Your course", ["program.university", "program.course", "program.level", "program.start_date", "uk.offer_conditions", "uk.accommodation_plan"]],
  ["Costs", ["funding.costs", "funding.scholarships"]],
  ["Your money", ["funding.funds", "funding.sponsor_income"]],
];

const FIELD_LABEL: Record<string, string> = {
  "student.full_name": "Full name",
  "academic.history": "Education",
  "academic.gap_explanation": "Work or gap after study",
  "academic.english_test": "English test",
  "program.university": "University",
  "program.course": "Course",
  "program.level": "Level",
  "program.start_date": "Start date",
  "uk.offer_conditions": "Offer conditions",
  "uk.accommodation_plan": "Accommodation",
  "funding.costs": "Cost",
  "funding.scholarships": "Scholarship",
  "funding.funds": "Funds",
  "funding.sponsor_income": "Sponsor income",
};

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null;

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

export function fmtMoney(amount: number | string, currency: string): string {
  const n = Number(amount);
  return `${currency} ${n.toLocaleString("en-GB", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

export function factLabel(f: Fact): string {
  const v = f.value_json;
  if (isObj(v) && typeof v.label === "string") return v.label;
  if (f.field_name === "funding.sponsor_income" && isObj(v) && v.earner) return `Sponsor income (${v.earner})`;
  return FIELD_LABEL[f.field_name] ?? f.field_name.split(".").pop()!.replace(/_/g, " ");
}

export function factValue(f: Fact): string {
  const v = f.value_json;
  if (f.field_name === "program.start_date") return fmtDate(String(v));
  if (isObj(v) && "annual_amount" in v) return `${fmtMoney(String(v.annual_amount), String(v.currency))} per year`;
  if (isObj(v) && "amount" in v) {
    const money = fmtMoney(String(v.amount), String(v.currency));
    return v.period === "annual" ? `${money} per year` : money;
  }
  if (v === null || v === undefined) return "—";
  return typeof v === "object" ? JSON.stringify(v) : String(v);
}

export function factNote(f: Fact): string {
  const v = f.value_json;
  if (!isObj(v)) return "";
  const notes: string[] = [];
  if (v.already_deducted) notes.push("already taken off the cost");
  if ("available_by" in v) notes.push(v.available_by ? `available by ${fmtDate(String(v.available_by))}` : "availability date not confirmed");
  if (v.kind === "loan") notes.push(v.sanction_confirmed ? "sanctioned" : "sanction not confirmed");
  if (v.holder) notes.push(`held by ${v.holder}`);
  return notes.join(" · ");
}

export function groupFacts(facts: Fact[]): [string, Fact[]][] {
  const placed = new Set<string>();
  const out: [string, Fact[]][] = [];
  for (const [title, fields] of GROUPS) {
    const rows = facts
      .filter((f) => fields.includes(f.field_name))
      .sort((a, b) => fields.indexOf(a.field_name) - fields.indexOf(b.field_name) || a.ref.localeCompare(b.ref));
    rows.forEach((f) => placed.add(f.ref));
    if (rows.length) out.push([title, rows]);
  }
  const rest = facts.filter((f) => !placed.has(f.ref));
  if (rest.length) out.push(["Other details", rest]);
  return out;
}
