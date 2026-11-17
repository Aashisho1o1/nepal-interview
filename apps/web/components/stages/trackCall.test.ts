import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "@/lib/api";
import { trackCall } from "./trackCall";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));
const post = vi.mocked(api);
const reply = (seconds_left: number, live = true) => ({ live, seconds_left, practice_ends_at: null });
const kinds = () => post.mock.calls.map(([, init]) => (init as { json: { kind: string } }).json.kind);

const callbacks = () => ({ onPhase: vi.fn(), onClock: vi.fn(), onNotice: vi.fn(), onEnded: vi.fn() });
let cb: { current: ReturnType<typeof callbacks> };
let call: ReturnType<typeof trackCall>;

beforeEach(() => {
  vi.useFakeTimers();
  post.mockReset();
  cb = { current: callbacks() };
  call = trackCall("s1", cb);
});
afterEach(() => {
  call.close();
  vi.useRealTimers();
});

// Runs ready() through its retry wait.
async function ready() {
  const done = call.ready("call_connected");
  await vi.advanceTimersByTimeAsync(2_000);
  await done;
}

test("ready() posts media_ready once and starts the clock", async () => {
  post.mockResolvedValue(reply(120));
  const start = performance.now();
  await ready();
  await call.ready("again");
  expect(kinds()).toEqual(["media_ready"]);
  expect(cb.current.onClock).toHaveBeenCalledExactlyOnceWith(start + 120_000);
  expect(cb.current.onPhase).toHaveBeenCalledWith("in_call");
  expect(cb.current.onEnded).not.toHaveBeenCalled();
});

test("a failed first try is retried and the clock still starts", async () => {
  post.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(reply(120));
  await ready();
  expect(kinds()).toEqual(["media_ready", "media_ready"]);
  expect(cb.current.onClock).toHaveBeenCalledOnce();
  expect(cb.current.onEnded).not.toHaveBeenCalled();
});

test("if the clock can't be started, the call ends once", async () => {
  post.mockRejectedValue(new Error("offline"));
  await ready();
  call.finish("user");
  expect(cb.current.onClock).not.toHaveBeenCalled();
  expect(cb.current.onEnded).toHaveBeenCalledExactlyOnceWith("connect_failed");
});

test("a session settled elsewhere ends the call once and stops the heartbeats", async () => {
  post.mockResolvedValueOnce(reply(120)).mockResolvedValue(reply(100, false));
  await ready();
  await vi.advanceTimersByTimeAsync(45_000);
  expect(kinds()).toEqual(["media_ready", "heartbeat"]);
  expect(cb.current.onEnded).toHaveBeenCalledExactlyOnceWith("settled_elsewhere");
});

test("finishing twice reports the end once", () => {
  call.finish("user");
  call.finish("deadline");
  expect(cb.current.onEnded).toHaveBeenCalledExactlyOnceWith("user");
});

test("a heartbeat moves the deadline earlier, never later", async () => {
  const start = performance.now();
  post.mockResolvedValueOnce(reply(120)); // ends at start + 120 s
  await ready();
  post.mockResolvedValueOnce(reply(110)); // heartbeat at 15 s: a slow reply, would end at 125 s
  await vi.advanceTimersByTimeAsync(15_000);
  post.mockResolvedValueOnce(reply(60)); // at 30 s: the phone slept, ends at 90 s
  await vi.advanceTimersByTimeAsync(15_000);
  expect(cb.current.onClock.mock.calls).toEqual([[start + 120_000], [start + 90_000]]);
});

test("replies that arrive after close() are ignored", async () => {
  let answer!: (r: ReturnType<typeof reply>) => void;
  post.mockResolvedValueOnce(reply(120)).mockReturnValueOnce(new Promise((r) => (answer = r)));
  await ready();
  await vi.advanceTimersByTimeAsync(15_000); // a heartbeat is out
  call.close();
  answer(reply(30));
  await vi.advanceTimersByTimeAsync(0);
  expect(cb.current.onClock).toHaveBeenCalledOnce(); // only the start

  // The same for a media_ready still out when the stage goes away.
  const other = trackCall("s2", cb);
  post.mockReturnValueOnce(new Promise((r) => (answer = r)));
  const done = other.ready("call_connected");
  await vi.advanceTimersByTimeAsync(0);
  other.close();
  answer(reply(30, false));
  await done;
  expect(cb.current.onClock).toHaveBeenCalledOnce();
  expect(cb.current.onEnded).not.toHaveBeenCalled();
});
