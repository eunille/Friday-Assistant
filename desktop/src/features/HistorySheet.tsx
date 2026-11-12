import { useEffect, useRef, useState, type FormEvent } from "react";
import { engine } from "../engine";
import type { AppState, Step } from "../store";

const STEP_MARK: Record<Step["status"], string> = { running: "…", done: "✓", failed: "!", declined: "✕" };

export function StepChips({ steps }: { steps: Step[] }) {
  if (!steps.length) return null;
  return (
    <div className="steps">
      {steps.map((step, i) => (
        <span className="chip mono" key={i}>
          {STEP_MARK[step.status]} {step.tool}
        </span>
      ))}
    </div>
  );
}

/** The conversation so far, with a box for typing. Closed unless asked for. */
export function HistorySheet({ app, open, onClose }: { app: AppState; open: boolean; onClose: () => void }) {
  const list = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");

  // Keep the newest message in view.
  useEffect(() => {
    if (open && list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [open, app.messages.length]);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  // Hover off while scrolling, so rows sliding under the cursor don't repaint.
  useEffect(() => {
    const element = list.current!;
    let timer = 0;
    const onScroll = () => {
      element.setAttribute("data-scrolling", "");
      clearTimeout(timer);
      timer = window.setTimeout(() => element.removeAttribute("data-scrolling"), 150);
    };
    element.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      element.removeEventListener("scroll", onScroll);
      clearTimeout(timer);
    };
  }, []);

  const send = (event: FormEvent) => {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText("");
    void engine.command(value);
  };

  return (
    <section className={`sheet ${open ? "open" : ""}`} aria-hidden={!open} aria-label="Conversation history">
      <header>
        <strong style={{ color: "var(--ink)" }}>Conversation</strong>
        <span>this session</span>
        <span className="spacer" />
        <button className="btn" onClick={onClose} tabIndex={open ? 0 : -1}>
          Close <kbd>Esc</kbd>
        </button>
      </header>

      <div className="messages" ref={list}>
        {app.messages.length === 0 && <p className="empty">Nothing said yet. Talk to Friday, or type below.</p>}
        {app.messages.map((message) => (
          <div className={`msg ${message.from}`} key={message.id}>
            <StepChips steps={message.steps} />
            {message.text}
          </div>
        ))}
      </div>

      <form className="prompt" onSubmit={send}>
        <input
          ref={input}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Type to Friday…"
          aria-label="Type to Friday"
          maxLength={2000}
          tabIndex={open ? 0 : -1}
        />
        <button className="btn primary" type="submit" disabled={!text.trim() || !app.connected} tabIndex={open ? 0 : -1}>
          Send
        </button>
      </form>
    </section>
  );
}
