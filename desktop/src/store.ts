// Everything the interface knows, built from the engine's event stream.
// `reduce` is a pure function so it can be tested without a browser.

export type VoiceState = "startup" | "idle" | "listening" | "thinking" | "speaking";

export interface Step {
  tool: string;
  status: "running" | "done" | "failed" | "declined";
}

export interface Message {
  id: number;
  from: "you" | "friday";
  text: string;
  steps: Step[];
}

export interface Approval {
  id: string;
  question: string;
}

export interface AppState {
  connected: boolean;
  state: VoiceState;
  heard: string;
  response: string;
  messages: Message[];
  steps: Step[]; // steps of the turn in progress
  approvals: Approval[];
  nextId: number;
}

export type EngineEvent = { type: string; [key: string]: unknown };

export const initialState: AppState = {
  connected: false,
  state: "startup",
  heard: "",
  response: "",
  messages: [],
  steps: [],
  approvals: [],
  nextId: 1,
};

const MAX_MESSAGES = 200;

function push(state: AppState, from: Message["from"], text: string, steps: Step[] = []): AppState {
  const message: Message = { id: state.nextId, from, text, steps };
  return { ...state, messages: [...state.messages, message].slice(-MAX_MESSAGES), nextId: state.nextId + 1 };
}

function finishStep(steps: Step[], tool: string, status: Step["status"]): Step[] {
  const index = steps.findLastIndex((s) => s.tool === tool && s.status === "running");
  if (index === -1) return [...steps, { tool, status }];
  return steps.map((s, i) => (i === index ? { ...s, status } : s));
}

export function reduce(state: AppState, event: EngineEvent): AppState {
  switch (event.type) {
    case "connected":
      return { ...state, connected: true };
    case "disconnected":
      return { ...state, connected: false, approvals: [] };
    case "snapshot":
      return {
        ...state,
        connected: true,
        state: (event.state as VoiceState) ?? state.state,
        heard: (event.heard as string) ?? "",
        response: (event.response as string) ?? "",
        approvals: (event.approvals as Approval[]) ?? [],
      };
    case "state":
      return { ...state, state: event.state as VoiceState };
    case "heard": {
      const text = String(event.text ?? "");
      if (!text) return { ...state, heard: "" };
      return { ...push(state, "you", text), heard: text, steps: [] };
    }
    case "speech_start": {
      const text = String(event.text ?? "");
      // The steps gathered so far belong to this reply.
      return { ...push(state, "friday", text, state.steps), response: text, state: "speaking", steps: [] };
    }
    case "speech_end":
      return state.state === "speaking" ? { ...state, state: "idle" } : state;
    case "agent": {
      const tool = String(event.tool ?? "");
      if (event.step === "tool_start") return { ...state, steps: [...state.steps, { tool, status: "running" }] };
      if (event.step === "tool_end") return { ...state, steps: finishStep(state.steps, tool, event.ok ? "done" : "failed") };
      if (event.step === "tool_declined") return { ...state, steps: finishStep(state.steps, tool, "declined") };
      return state;
    }
    case "approval_request":
      return { ...state, approvals: [...state.approvals, { id: String(event.id), question: String(event.question) }] };
    case "approval_resolved":
      return { ...state, approvals: state.approvals.filter((a) => a.id !== event.id) };
    default:
      return state;
  }
}

// --- a tiny store: React reads it with useSyncExternalStore -----------------

let current = initialState;
const listeners = new Set<() => void>();

export const store = {
  get: () => current,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  dispatch(event: EngineEvent) {
    const next = reduce(current, event);
    if (next !== current) {
      current = next;
      listeners.forEach((l) => l());
    }
  },
};

// Voice levels arrive ~20 times a second. They bypass React entirely: the
// visualiser reads this object inside its own animation frame.
export const levels = {
  mic: new Array<number>(16).fill(0),
  voice: new Array<number>(16).fill(0),
  at: { mic: 0, voice: 0 },
};

export function setLevels(source: "mic" | "voice", bands: number[], now = performance.now()) {
  levels[source] = bands;
  levels.at[source] = now;
}
