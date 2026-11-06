"use client";

// The video / voice choice on the practice page. Native radio inputs inside styled
// labels: keyboard and screen readers get a real choice.

import { TIERS } from "@/lib/copy";

export type TierOption = {
  id: string;
  modality: "avatar" | "voice";
  label?: string; // tells apart two interviewers of one kind
  left?: string | null; // e.g. "1 session left"
  disabled?: boolean;
  note?: string; // why it's disabled
};

type Props = { options: TierOption[]; value: string | null; onChange: (id: string) => void; name?: string };

export default function TierCards({ options, value, onChange, name = "tier" }: Props) {
  return (
    <div className="tiers" role="radiogroup" aria-label="Interviewer">
      {options.map((o) => {
        const t = TIERS[o.modality];
        return (
          <label key={o.id} className="tier" data-selected={value === o.id} aria-disabled={o.disabled || undefined}>
            <input type="radio" name={name} value={o.id} checked={value === o.id} disabled={o.disabled} onChange={() => onChange(o.id)} />
            <span className="dot" aria-hidden="true" />
            {o.modality === "avatar" ? <VideoIcon /> : <VoiceIcon />}
            <span className="tier-title">{o.label ?? t.title}</span>
            <span className="small">{t.desc}</span>
            <span className="chips">
              <span className="chip chip--outline">{t.chip}</span>
              {o.disabled ? (
                <span className="chip chip--outline">{o.note ?? "Not available right now"}</span>
              ) : (
                o.left && <span className="chip chip--outline nums">{o.left}</span>
              )}
            </span>
          </label>
        );
      })}
    </div>
  );
}

function VideoIcon() {
  return (
    <svg viewBox="0 0 28 28" aria-hidden="true">
      <rect x="3" y="7.5" width="15" height="13" rx="3" />
      <path d="M18 12l7-3.5v11L18 16z" />
    </svg>
  );
}

function VoiceIcon() {
  return (
    <svg viewBox="0 0 28 28" aria-hidden="true">
      <path d="M5 11v6M9.5 7v14M14 4v20M18.5 8v12M23 11v6" />
    </svg>
  );
}
