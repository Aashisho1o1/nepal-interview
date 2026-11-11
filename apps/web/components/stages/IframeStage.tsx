"use client";

// Any vendor that gives us an iframe URL: LiveAvatar embeds, Tavus conversation links,
// and similar. We cannot see inside a cross-origin iframe, so this stage reports the
// lifecycle the server needs (clock start, heartbeats) from what the page *can* see:
// the iframe loading, focus moving into it, and any postMessage events the vendor sends.

import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import type { IframeLaunch, StageProps } from "@/lib/providers";

const HEARTBEAT_MS = 15_000;
const CLOCK_RETRY_MS = 2_000;
const LOAD_WARN_MS = 25_000;
const MAX_MESSAGE_TYPES = 20;

type EventReply = { live: boolean; practice_ends_at: number | null };

export default function IframeStage({ sessionId, launch, onPhase, onClock, onNotice, onEnded }: StageProps<IframeLaunch>) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const mountedAt = useRef(0); // set when the call mounts (render must stay pure)
  const loadedAt = useRef<number | null>(null);
  const started = useRef(false);
  const unmounted = useRef(false);
  // Keep the latest callbacks without re-running effects (and re-mounting the call).
  const cb = useRef({ onPhase, onClock, onNotice, onEnded });
  useEffect(() => {
    cb.current = { onPhase, onClock, onNotice, onEnded };
  });

  const post = (kind: string, payload: Record<string, unknown> = {}) =>
    api<EventReply>(`/sessions/${sessionId}/client-events`, { method: "POST", json: { kind, payload } });

  // Start the server-owned practice clock exactly once.
  const startClock = useRef(async (trigger: string) => {
    if (started.current) return;
    started.current = true;
    const payload = {
      trigger,
      load_ms: loadedAt.current ? Math.round(loadedAt.current - mountedAt.current) : null,
      ready_ms: Math.round(performance.now() - mountedAt.current),
    };
    // If the server can't be told, end the call (the session is refunded) rather than
    // let it run uncounted.
    for (const wait of [0, CLOCK_RETRY_MS]) {
      await new Promise((resolve) => setTimeout(resolve, wait));
      if (unmounted.current) return;
      try {
        const r = await post("media_ready", payload);
        if (unmounted.current) return;
        if (r.practice_ends_at) cb.current.onClock(r.practice_ends_at * 1000);
        cb.current.onPhase("in_call");
        if (!r.live) cb.current.onEnded("settled_elsewhere");
        return;
      } catch {
        /* try once more */
      }
    }
    cb.current.onEnded("connect_failed");
  });

  useEffect(() => {
    mountedAt.current = performance.now();
    unmounted.current = false;
    const frame = frameRef.current;
    const seenTypes = new Set<string>();

    // A click into a cross-origin iframe moves focus out of our window.
    const onBlur = () =>
      setTimeout(() => {
        if (document.activeElement === frame && launch.clock_start === "on_interaction") {
          void startClock.current("interaction");
        }
      }, 0);

    // Log what the vendor tells the parent page (event names only, never content), so we
    // can learn its events and later start/stop the clock precisely.
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== launch.origin || e.source !== frame?.contentWindow) return;
      const d = e.data as Record<string, unknown> | string;
      const type = typeof d === "string" ? d.slice(0, 60) : String(d?.type ?? d?.event ?? d?.action ?? "object").slice(0, 60);
      if (!seenTypes.has(type) && seenTypes.size < MAX_MESSAGE_TYPES) {
        seenTypes.add(type);
        void post("metric", { vendor_message: type, at_ms: Math.round(performance.now() - mountedAt.current) }).catch(() => undefined);
      }
    };

    const loadWarn = setTimeout(() => {
      if (loadedAt.current === null) {
        cb.current.onNotice("The interviewer is taking a while to load. Check your connection.");
        void post("metric", { slow_load_ms: LOAD_WARN_MS }).catch(() => undefined);
      }
    }, LOAD_WARN_MS);

    const heartbeat = setInterval(async () => {
      if (!started.current) return;
      try {
        const r = await post("heartbeat");
        if (!r.live) cb.current.onEnded("settled_elsewhere");
      } catch {
        /* transient; the server tolerates missed heartbeats */
      }
    }, HEARTBEAT_MS);

    window.addEventListener("blur", onBlur);
    window.addEventListener("message", onMessage);
    return () => {
      unmounted.current = true;
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("message", onMessage);
      clearTimeout(loadWarn);
      clearInterval(heartbeat);
    };
    // The launch for a session never changes; run once per mounted call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onLoad() {
    loadedAt.current = performance.now();
    void post("metric", { load_ms: Math.round(loadedAt.current - mountedAt.current) }).catch(() => undefined);
    if (launch.clock_start === "on_load") {
      void startClock.current("load");
      return;
    }
    cb.current.onPhase("waiting_start");
    // If the embed starts by itself (no click needed), don't wait forever.
    setTimeout(() => void startClock.current("fallback_timeout"), launch.clock_fallback_ms);
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
