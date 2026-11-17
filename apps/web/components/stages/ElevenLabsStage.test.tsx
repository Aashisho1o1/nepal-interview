// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, test, vi } from "vitest";
import ElevenLabsStage from "./ElevenLabsStage";

type Options = { onDisconnect: (d: { reason: string }) => void };
const sdk = vi.hoisted(() => ({ startSession: vi.fn() }));
vi.mock("@elevenlabs/react", () => ({ Conversation: sdk }));
vi.mock("@/lib/api", () => ({ api: vi.fn(() => new Promise(() => undefined)) }));
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const launch = { kind: "voice_call", connection_type: "webrtc", conversation_token: "t", dynamic_variables: {} } as const;
const tick = () => act(() => new Promise((r) => setTimeout(r, 0)));

async function mount() {
  const onEnded = vi.fn();
  const root = createRoot(document.createElement("div"));
  await act(() => root.render(<ElevenLabsStage sessionId="s1" launch={launch} onPhase={vi.fn()} onClock={vi.fn()} onNotice={vi.fn()} onEnded={onEnded} />));
  await tick(); // the deferred start
  return { root, onEnded };
}

test("leaving while the call is still connecting ends it once it connects", async () => {
  let connect!: (conv: { endSession: () => Promise<void> }) => void;
  sdk.startSession.mockReturnValueOnce(new Promise((r) => (connect = r)));
  const { root } = await mount();
  act(() => root.unmount());
  const endSession = vi.fn(async () => undefined);
  connect({ endSession });
  await tick();
  expect(endSession).toHaveBeenCalledOnce();
});

test("the agent hanging up ends the call as agent_ended", async () => {
  sdk.startSession.mockResolvedValueOnce({ endSession: vi.fn(async () => undefined) });
  const { root, onEnded } = await mount();
  const [options] = sdk.startSession.mock.lastCall as [Options];
  options.onDisconnect({ reason: "agent" });
  expect(onEnded).toHaveBeenCalledExactlyOnceWith("agent_ended");
  act(() => root.unmount());
});
