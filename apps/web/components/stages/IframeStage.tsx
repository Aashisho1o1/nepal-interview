"use client";

// Any vendor that gives us an iframe URL: LiveAvatar embeds, Tavus conversation links,
// and similar. We cannot see inside a cross-origin iframe, so the clock starts (through
// trackCall) on what the page *can* see: the iframe loading, focus moving into it, or a
// fallback timer. Any postMessage events the vendor sends are logged as metrics.

import { useEffect, useRef } from "react";
import type { IframeLaunch, StageProps } from "@/lib/providers";
import { trackCall } from "./trackCall";

const LOAD_WARN_MS = 25_000;
const MAX_MESSAGE_TYPES = 20;

export default function IframeStage({ sessionId, launch, onPhase, onClock, onNotice, onEnded }: StageProps<IframeLaunch>) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const call = useRef<ReturnType<typeof trackCall> | null>(null);
  const mountedAt = useRef(0); // set when the call mounts (render must stay pure)
  const loaded = useRef(false);
  // Keep the latest callbacks without re-running effects (and re-mounting the call).
  const cb = useRef({ onPhase, onClock, onNotice, onEnded });
  useEffect(() => {
    cb.current = { onPhase, onClock, onNotice, onEnded };
  });

  useEffect(() => {
    const c = trackCall(sessionId, cb);
    call.current = c;
    mountedAt.current = performance.now();
    const frame = frameRef.current;
    const seenTypes = new Set<string>();

    // A click into a cross-origin iframe moves focus out of our window.
    const onBlur = () =>
      setTimeout(() => {
        if (document.activeElement === frame && launch.clock_start === "on_interaction") void c.ready("interaction");
      }, 0);

    // Log what the vendor tells the parent page (event names only, never content), so we
    // can learn its events and later start/stop the clock precisely.
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== launch.origin || e.source !== frame?.contentWindow) return;
      const d = e.data as Record<string, unknown> | string;
      const type = typeof d === "string" ? d.slice(0, 60) : String(d?.type ?? d?.event ?? d?.action ?? "object").slice(0, 60);
      if (!seenTypes.has(type) && seenTypes.size < MAX_MESSAGE_TYPES) {
        seenTypes.add(type);
        c.metric({ vendor_message: type, at_ms: Math.round(performance.now() - mountedAt.current) });
      }
    };

    const loadWarn = setTimeout(() => {
      if (!loaded.current) {
        cb.current.onNotice("The interviewer is taking a while to load. Check your connection.");
        c.metric({ slow_load_ms: LOAD_WARN_MS });
      }
    }, LOAD_WARN_MS);

    window.addEventListener("blur", onBlur);
    window.addEventListener("message", onMessage);
    return () => {
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("message", onMessage);
      clearTimeout(loadWarn);
      c.close();
    };
    // The launch for a session never changes; run once per mounted call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onLoad() {
    loaded.current = true;
    call.current?.metric({ load_ms: Math.round(performance.now() - mountedAt.current) });
    if (call.current?.isConnected()) return; // the clock already started (a reload inside the embed)
    if (launch.clock_start === "on_load") return void call.current?.ready("load");
    cb.current.onPhase("waiting_start");
    // If the embed starts by itself (no click needed), don't wait forever.
    setTimeout(() => void call.current?.ready("fallback_timeout"), launch.clock_fallback_ms);
  }

  return (
    <iframe
      ref={frameRef}
      className="stage-frame"
      src={launch.url}
      allow={launch.allow}
      title={launch.title}
      style={{ aspectRatio: launch.aspect_ratio }}
      referrerPolicy="strict-origin-when-cross-origin"
      onLoad={onLoad}
    />
  );
}
