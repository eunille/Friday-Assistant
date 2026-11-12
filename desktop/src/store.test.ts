import { describe, expect, it } from "vitest";
import { initialState, reduce, type AppState, type EngineEvent } from "./store";

const run = (...events: EngineEvent[]): AppState => events.reduce(reduce, initialState);

describe("reduce", () => {
  it("tracks the voice state", () => {
    expect(run({ type: "state", state: "listening" }).state).toBe("listening");
  });

  it("adopts the engine's snapshot on connect", () => {
    const state = run({ type: "snapshot", state: "idle", heard: "hi", response: "Hello, boss.",
      approvals: [{ id: "a", question: "Send?" }] });
    expect(state).toMatchObject({ connected: true, state: "idle", response: "Hello, boss." });
    expect(state.approvals).toHaveLength(1);
  });

  it("records what was heard and what Friday said as messages", () => {
    const state = run({ type: "heard", text: "what time is it" }, { type: "speech_start", text: "It's four." });
    expect(state.messages.map((m) => [m.from, m.text])).toEqual([["you", "what time is it"], ["friday", "It's four."]]);
    expect(state.state).toBe("speaking");
    expect(state.response).toBe("It's four.");
  });

  it("clearing 'heard' does not add an empty message", () => {
    expect(run({ type: "heard", text: "" }).messages).toHaveLength(0);
  });

  it("attaches the agent's steps to the reply they produced", () => {
    const state = run(
      { type: "heard", text: "how's bitcoin" },
      { type: "agent", step: "tool_start", tool: "web_search" },
      { type: "agent", step: "tool_end", tool: "web_search", ok: true },
      { type: "speech_start", text: "Up four percent." },
    );
    expect(state.messages[1].steps).toEqual([{ tool: "web_search", status: "done" }]);
    expect(state.steps).toEqual([]);
  });

  it("marks a failed and a declined tool", () => {
    const state = run(
      { type: "agent", step: "tool_start", tool: "read_page" },
      { type: "agent", step: "tool_end", tool: "read_page", ok: false },
      { type: "agent", step: "tool_declined", tool: "sign_in" },
    );
    expect(state.steps).toEqual([{ tool: "read_page", status: "failed" }, { tool: "sign_in", status: "declined" }]);
  });

  it("returns to idle when speech ends", () => {
    expect(run({ type: "speech_start", text: "Hi." }, { type: "speech_end" }).state).toBe("idle");
  });

  it("shows an approval until it is resolved", () => {
    const asked = run({ type: "approval_request", id: "x1", question: "Sign in?" });
    expect(asked.approvals).toEqual([{ id: "x1", question: "Sign in?" }]);
    expect(reduce(asked, { type: "approval_resolved", id: "x1", allowed: true }).approvals).toEqual([]);
  });

  it("drops pending approvals when the engine disconnects", () => {
    const state = run({ type: "approval_request", id: "x1", question: "Sign in?" }, { type: "disconnected" });
    expect(state).toMatchObject({ connected: false, approvals: [] });
  });

  it("ignores events it doesn't know", () => {
    expect(run({ type: "calibration", ambient: 3 })).toBe(initialState);
  });

  it("keeps at most 200 messages", () => {
    const events = Array.from({ length: 250 }, (_, i) => ({ type: "heard", text: `m${i}` }));
    const state = run(...events);
    expect(state.messages).toHaveLength(200);
    expect(state.messages.at(-1)!.text).toBe("m249");
  });
});
