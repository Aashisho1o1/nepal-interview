// Stage registry: launch.kind -> component. Add a vendor SDK here (e.g. "elevenlabs")
// only when it cannot be shown as an iframe.

import type { ComponentType } from "react";
import type { Launch, StageProps } from "@/lib/providers";
import IframeStage from "./IframeStage";
import LiveKitStage from "./LiveKitStage";

export const STAGES: { [K in Launch["kind"]]: ComponentType<StageProps<Extract<Launch, { kind: K }>>> } = {
  livekit: LiveKitStage,
  iframe: IframeStage,
};

/** Stages whose session lifecycle the browser reports (the page enforces the deadline). */
export const CLIENT_DRIVEN: ReadonlySet<Launch["kind"]> = new Set(["iframe"]);
