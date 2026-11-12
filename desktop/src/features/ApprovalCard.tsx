import { engine } from "../engine";
import type { Approval } from "../store";

/** Shown only when Friday needs a yes or no. It also asks out loud. */
export function ApprovalCard({ approval }: { approval: Approval }) {
  return (
    <div className="approval" role="alertdialog" aria-label="Friday needs your approval">
      <div className="eyebrow">Friday is asking</div>
      <p>{approval.question}</p>
      <div className="actions">
        <button className="btn primary" autoFocus onClick={() => engine.answer(approval.id, true)}>
          Allow
        </button>
        <button className="btn" onClick={() => engine.answer(approval.id, false)}>
          Deny
        </button>
        <span className="say">or say “yes” / “no”</span>
      </div>
    </div>
  );
}
