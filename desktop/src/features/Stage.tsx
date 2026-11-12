import { useEffect, useState } from "react";
import { engine } from "../engine";
import type { AppState } from "../store";
import { ApprovalCard } from "./ApprovalCard";
import { HistorySheet } from "./HistorySheet";
import { Visualizer } from "./Visualizer";

const STATUS: Record<AppState["state"], string> = {
  startup: "Starting up",
  idle: "Say “Hey Jarvis”",
  listening: "Listening",
  thinking: "Working on it",
  speaking: "Speaking",
};

const STEP_TEXT = { running: "working", done: "done", failed: "failed", declined: "declined" } as const;

/** The full view: the voice is the screen. History is a sheet you pull up. */
export function Stage({ app, startWithHistory = false }: { app: AppState; startWithHistory?: boolean }) {
  const [history, setHistory] = useState(startWithHistory);
  const approval = app.approvals[0];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLInputElement;
      if (event.key === "Escape") setHistory(false);
      else if (event.code === "Space" && !typing && !event.repeat) {
        event.preventDefault();
        void (app.state === "speaking" ? engine.stop() : engine.listen());
      } else if (event.key.toLowerCase() === "h" && !typing) setHistory((open) => !open);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [app.state]);

  // What Friday did for the latest reply, plus anything still running.
  const lastReply = [...app.messages].reverse().find((m) => m.from === "friday");
  const steps = app.steps.length ? app.steps : (lastReply?.steps ?? []);
  const status = app.connected ? STATUS[app.state] : "Starting the engine…";

  return (
    <div className="full">
      <div className="topbar">
        <span className={`dot ${app.connected ? "on" : "off"}`} />
        <strong>Friday</strong>
        <span>{app.connected ? "ready" : "starting"}</span>
        <span className="spacer" />
        <button className="btn" onClick={() => setHistory((open) => !open)} aria-expanded={history}>
          History <kbd>H</kbd>
        </button>
        <button className="btn" onClick={() => window.friday?.collapse()} title="Shrink to the widget">
          Widget
        </button>
      </div>

      <div className="body">
        <main className={`stage ${approval ? "asking" : ""}`}>
          <div className={`status ${app.state}`} aria-live="polite">{status}</div>
          <Visualizer state={app.connected ? app.state : "idle"} bars={40} />

          {approval ? (
            <ApprovalCard approval={approval} />
          ) : (
            <>
              <div className={`caption ${app.response ? "" : "muted"}`} key={app.response} aria-live="polite">
                {app.response || "I'm here when you need me, boss."}
              </div>
              <div className="heard">{app.heard ? `You said: “${app.heard}”` : ""}</div>
            </>
          )}

          <div className="hints">
            <span className="chip"><kbd>Space</kbd> {app.state === "speaking" ? "stop" : "talk"}</span>
            <span className="chip"><kbd>H</kbd> history &amp; typing</span>
          </div>
        </main>

        <aside className="rail" aria-label="Activity">
          <h2>Just now</h2>
          {steps.length === 0 && <div className="empty">Nothing yet.</div>}
          {steps.map((step, i) => (
            <div className="row" key={i}>
              <span className="mono">{step.tool}</span>
              <span className={step.status}>{STEP_TEXT[step.status]}</span>
            </div>
          ))}
          <div className="credit">Voice by Underdog Woof</div>
        </aside>
      </div>

      <HistorySheet app={app} open={history} onClose={() => setHistory(false)} />
    </div>
  );
}
