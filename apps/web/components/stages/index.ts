// Stage registry: launch.kind -> component. Add a vendor SDK here only when it cannot
// be shown as an iframe.

import dynamic from "next/dynamic";
import type { ComponentType } from "react";
import type { Launch, StageProps } from "@/lib/providers";

// Loaded when a call starts, so no vendor code is in the page until then.
const IframeStage = dynamic(() => import("./IframeStage"));
const ElevenLabsStage = dynamic(() => import("./ElevenLabsStage"));
const LiveAvatarStage = dynamic(() => import("./LiveAvatarStage"));
const KeyframeStage = dynamic(() => import("./KeyframeStage"));

export const STAGES: { [K in Launch["kind"]]: ComponentType<StageProps<Extract<Launch, { kind: K }>>> } = {
  iframe: IframeStage,
  voice_call: ElevenLabsStage,
  video_a: LiveAvatarStage,
  video_b: KeyframeStage,
};
