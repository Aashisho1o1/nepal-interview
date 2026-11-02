// Stage registry: launch.kind -> component. Add a vendor SDK here only when it cannot
// be shown as an iframe.

import type { ComponentType } from "react";
import type { Launch, StageProps } from "@/lib/providers";
import ElevenLabsStage from "./ElevenLabsStage";
import IframeStage from "./IframeStage";
import LiveKitStage from "./LiveKitStage";

export const STAGES: { [K in Launch["kind"]]: ComponentType<StageProps<Extract<Launch, { kind: K }>>> } = {
  livekit: LiveKitStage,
  iframe: IframeStage,
  elevenlabs: ElevenLabsStage,
};

/** Stages whose session lifecycle the browser reports (the page enforces the deadline). */
export const CLIENT_DRIVEN: ReadonlySet<Launch["kind"]> = new Set(["iframe", "elevenlabs"]);
