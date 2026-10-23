import { Image, Network } from "lucide-react";
import { workflowGraphPngUrl } from "../api";

/** Static architecture image generated locally from `build_graph().compile()` on the backend. */
export default function LangGraphPng() {
  return (
    <section aria-label="LangGraph architecture PNG" className="rounded-2xl border border-border bg-surface p-4 shadow-soft sm:p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted"><Image size={13} aria-hidden /> Static LangGraph diagram</p>
          <h2 className="mt-1 text-[16px] font-semibold leading-snug">Compiled workflow architecture</h2>
          <p className="mt-1 text-[12.5px] text-muted">This PNG is generated locally by the backend from the real LangGraph nodes and edges. It is a documentation view; use Workflow graph for live run status.</p>
        </div>
        <span className="ep-chip"><Network size={12} aria-hidden /> backend generated</span>
      </header>
      <a href={workflowGraphPngUrl()} target="_blank" rel="noreferrer" className="mt-5 block overflow-auto rounded-xl border border-border bg-surface-2 p-3" title="Open the full-size LangGraph PNG">
        <img src={workflowGraphPngUrl()} alt="EventPilot LangGraph workflow: specialists converge through event manager and review before the final plan." className="mx-auto min-w-[720px] max-w-none" />
      </a>
    </section>
  );
}
