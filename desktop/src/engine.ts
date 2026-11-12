// Connection to the Friday engine: one WebSocket for events, fetch for actions.
import { setLevels, store, type EngineEvent } from "./store";

interface EngineInfo {
  port: number;
  token: string;
}

declare global {
  interface Window {
    friday?: {
      engine(): Promise<EngineInfo | null>;
      expand(): void;
      collapse(): void;
      resizeWidget(height: number): void;
      quit(): void;
    };
  }
}

let info: EngineInfo | null = null;
let socket: WebSocket | null = null;
let retry = 0;

function handle(event: EngineEvent) {
  if (event.type === "level") {
    setLevels(event.source as "mic" | "voice", event.bands as number[]);
    return;
  }
  store.dispatch(event);
}

function open() {
  if (!info) return;
  socket = new WebSocket(`ws://127.0.0.1:${info.port}/ws?token=${encodeURIComponent(info.token)}`);
  socket.onopen = () => {
    retry = 0;
    store.dispatch({ type: "connected" });
  };
  socket.onmessage = (message) => {
    try {
      handle(JSON.parse(message.data));
    } catch {
      /* ignore a malformed frame */
    }
  };
  socket.onclose = () => {
    store.dispatch({ type: "disconnected" });
    // The engine takes a while to load its speech models; keep trying.
    retry = Math.min(retry + 1, 10);
    setTimeout(open, 300 * retry);
  };
}

export async function connect() {
  info = (await window.friday?.engine()) ?? null;
  if (info) open();
}

async function post(path: string, body?: unknown) {
  if (!info) return null;
  const response = await fetch(`http://127.0.0.1:${info.port}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${info.token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return response.ok ? response.json() : null;
}

export const engine = {
  /** Act on typed text as if it had been spoken. */
  command: (text: string) => post("/command", { text }),
  /** Start listening without the wake word. */
  listen: () => post("/activate"),
  /** Stop Friday mid-sentence. */
  stop: () => post("/stop"),
  answer: (id: string, allow: boolean) => post(`/approvals/${id}`, { allow }),
};
