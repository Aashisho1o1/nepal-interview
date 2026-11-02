// Stage registry: launch.kind -> component. Add a vendor SDK here only when it cannot
// be shown as an iframe.

import type { ComponentType } from "react";
import type { Launch, StageProps } from "@/lib/providers";
import ElevenLabsStage from "./ElevenLabsStage";
import IframeStage from "./IframeStage";

export const STAGES: { [K in Launch["kind"]]: ComponentType<StageProps<Extract<Launch, { kind: K }>>> } = {
  iframe: IframeStage,
  elevenlabs: ElevenLabsStage,
};
