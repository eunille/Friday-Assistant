import { useEffect, useRef } from "react";
import { levels, type VoiceState } from "../store";

interface Props {
  state: VoiceState;
  bars: number;
  className?: string;
}

const STALE_MS = 250; // levels older than this are treated as silence

/** Live frequency bars: the mic while listening, Friday's voice while speaking. */
export function Visualizer({ state, bars, className = "viz" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current!;
    const context = canvas.getContext("2d")!;
    const shown = new Array<number>(bars).fill(0);
    const style = getComputedStyle(document.documentElement);
    const colour = {
      speaking: style.getPropertyValue("--accent").trim(),
      thinking: style.getPropertyValue("--accent").trim(),
      listening: style.getPropertyValue("--green").trim(),
      idle: style.getPropertyValue("--ink-3").trim(),
    };
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;

    const draw = (now: number) => {
      const ratio = devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);

      const mode = stateRef.current;
      const source = mode === "listening" ? "mic" : mode === "speaking" ? "voice" : null;
      const fresh = source !== null && now - levels.at[source] < STALE_MS;
      const bands = fresh ? levels[source!] : null;

      const gap = Math.max(2, Math.min(5, width / bars / 3));
      const barWidth = Math.max(2, (width - gap * (bars - 1)) / bars);
      context.fillStyle = mode === "speaking" || mode === "thinking" ? colour.speaking
        : mode === "listening" ? colour.listening : colour.idle;

      for (let i = 0; i < bars; i++) {
        let target = 0.06;
        if (bands) {
          // Mirror the spectrum around the centre so the shape reads as a voice.
          const fromCentre = Math.abs(i - (bars - 1) / 2) / ((bars - 1) / 2);
          const band = Math.min(bands.length - 1, Math.round(fromCentre * (bands.length - 1)));
          target = Math.max(0.06, bands[band]);
        } else if (mode === "thinking" && !still) {
          target = 0.14 + 0.1 * Math.sin(now / 260 + i * 0.5);
        }
        // Rise fast, fall slowly.
        shown[i] += (target - shown[i]) * (target > shown[i] ? 0.55 : 0.16);
        const barHeight = Math.max(3, shown[i] * height);
        const x = i * (barWidth + gap);
        context.beginPath();
        context.roundRect(x, (height - barHeight) / 2, barWidth, barHeight, barWidth / 2);
        context.fill();
      }
      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [bars]);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
