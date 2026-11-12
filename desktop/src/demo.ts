// Fake engine activity, used only by `npm run smoke` screenshots and for
// working on the interface without a microphone: open #/main?demo=speaking
import { setLevels, store } from "./store";

export type Demo = "speaking" | "approval" | "history";

export function startDemo(demo: Demo) {
  store.dispatch({ type: "connected" });
  store.dispatch({ type: "heard", text: "how's bitcoin doing today" });
  store.dispatch({ type: "agent", step: "tool_start", tool: "web_search" });
  store.dispatch({ type: "agent", step: "tool_end", tool: "web_search", ok: true });
  store.dispatch({ type: "speech_start", text: "Bitcoin's up four percent, boss. Strongest move in two weeks." });

  if (demo === "history") {
    store.dispatch({ type: "speech_end" });
    store.dispatch({ type: "heard", text: "open github and check my notifications" });
    store.dispatch({ type: "agent", step: "tool_start", tool: "open_website" });
    store.dispatch({ type: "agent", step: "tool_end", tool: "open_website", ok: true });
    store.dispatch({ type: "agent", step: "tool_start", tool: "read_current_page" });
    store.dispatch({ type: "agent", step: "tool_end", tool: "read_current_page", ok: true });
    store.dispatch({ type: "speech_start", text: "Three new notifications. Two are review requests, one is a failed build." });
    store.dispatch({ type: "speech_end" });
  }
  if (demo === "approval") {
    store.dispatch({ type: "approval_request", id: "demo", question: "Sign in to github.com with your saved session?" });
  }

  // A moving, voice-shaped spectrum.
  setInterval(() => {
    const t = performance.now() / 1000;
    const bands = Array.from({ length: 16 }, (_, i) => {
      const shape = Math.exp(-((i - 4) ** 2) / 18);
      return Math.max(0, Math.min(1, shape * (0.55 + 0.45 * Math.sin(t * 7 + i * 1.3)) + 0.08 * Math.sin(t * 13 + i)));
    });
    setLevels("voice", bands);
  }, 50);
}
