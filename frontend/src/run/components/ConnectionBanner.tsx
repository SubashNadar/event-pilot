import { CheckCircle2, WifiOff } from "lucide-react";
import type { ConnectionState } from "../types";

/** Transport status only; run errors are shown inside the run panel. */
export default function ConnectionBanner({ state }: { state: ConnectionState }) {
  if (state === "reconnecting") {
    return (
      <div role="status" className="flex items-center justify-center gap-2 rounded-xl bg-warn/10 px-4 py-2 text-[13px] text-warn">
        <WifiOff size={14} aria-hidden /> Connection lost. Reconnecting — the plan keeps running and will pick up where it left off.
      </div>
    );
  }
  if (state === "reconnected") {
    return (
      <div role="status" className="flex items-center justify-center gap-2 rounded-xl bg-success/10 px-4 py-2 text-[13px] text-success">
        <CheckCircle2 size={14} aria-hidden /> Reconnected.
      </div>
    );
  }
  return null;
}
