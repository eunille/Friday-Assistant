import { useEffect, useRef } from "react";
import { engine } from "../engine";
import type { AppState } from "../store";
import { ApprovalCard } from "./ApprovalCard";
import { Visualizer } from "./Visualizer";

const LABEL: Record<AppState["state"], string> = {
  startup: "Starting",
  idle: "Friday",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

/** The small always-on-top pill. Grows a card above itself when Friday asks something. */
export function Widget({ app }: { app: AppState }) {
  const root = useRef<HTMLDivElement>(null);
  const approval = app.approvals[0];

  // Ask the shell to size the window to the pill, plus the card when there is one.
  useEffect(() => {
    const element = root.current!;
    const report = () => {
      const content = [...element.children].reduce((sum, child) => sum + (child as HTMLElement).offsetHeight, 0);
      window.friday?.resizeWidget(content + 16 + (element.children.length - 1) * 8);
    };
    report();
    const observer = new ResizeObserver(report);
    [...element.children].forEach((child) => observer.observe(child));
    return () => observer.disconnect();
  }, [approval?.id]);

  const label = app.connected ? LABEL[app.state] : "Starting";

  return (
    <div className="widget" ref={root}>
      {approval && <ApprovalCard approval={approval} />}
      <div className="pill">
        <span className={`dot ${app.connected ? "on" : "off"}`} title={app.connected ? "Engine running" : "Engine starting"} />
        <span className="label">{label}</span>
        <Visualizer state={app.connected ? app.state : "idle"} bars={18} />
        {app.state === "speaking" ? (
          <button className="icon-btn" aria-label="Stop speaking" title="Stop speaking" onClick={() => engine.stop()}>
            ■
          </button>
        ) : (
          <button className="icon-btn" aria-label="Talk to Friday" title="Talk to Friday" onClick={() => engine.listen()}>
            ●
          </button>
        )}
        <button className="icon-btn" aria-label="Open full view" title="Open full view" onClick={() => window.friday?.expand()}>
          ⤢
        </button>
      </div>
    </div>
  );
}
