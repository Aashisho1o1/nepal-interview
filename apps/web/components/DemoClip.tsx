"use client";

// Recorded demo on the home page. Only the poster of the chosen clip loads until someone
// presses play. To replace a clip, add a new -v2 file: these files are cached for a year.

import { useState } from "react";

const CLIPS = {
  video: { label: "Video call", name: "video" },
  voice: { label: "Voice call", name: "voice" },
} as const;
type Mode = keyof typeof CLIPS;

export default function DemoClip({ onTry }: { onTry: () => void }) {
  const [mode, setMode] = useState<Mode>("video");
  const [ended, setEnded] = useState(false);
  const { name } = CLIPS[mode];

  return (
    <div className="clip">
      <div className="seg" role="group" aria-label="Choose a demo">
        {(Object.keys(CLIPS) as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={mode === m}
            onClick={() => {
              setMode(m);
              setEnded(false);
            }}
          >
            {CLIPS[m].label}
          </button>
        ))}
      </div>
      {/* key: a new element per clip, so switching stops the other one. */}
      <video key={mode} controls playsInline preload="none" poster={`/demo/${name}-poster-v1.jpg`} onEnded={() => setEnded(true)}>
        <source src={`/demo/${name}-call-v1.mp4`} type="video/mp4" />
        <track default kind="captions" srcLang="en" label="English" src={`/demo/${name}-call-v1.vtt`} />
      </video>
      <p className="caption">Recorded demo. Fictional AI interviewer, not UKVI or a university.</p>
      {ended && (
        <p className="small">
          Ready to try?{" "}
          <button type="button" className="btn btn-ghost" onClick={onTry}>Start practising free</button>
        </p>
      )}
    </div>
  );
}
