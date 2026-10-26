import clsx from "clsx";
import type { PlanPreview as PlanPreviewData } from "../types";

const money = (value: number) => `₹${Math.round(value).toLocaleString("en-IN")}`;

/**
 * The generated plan, shown in the approval card so the owner can read it before
 * approving or sending it back. Lists the venue, the budget against the approved
 * amount, the agenda, and the risks.
 */
export default function PlanPreview({ preview, compact = false }: { preview: PlanPreviewData; compact?: boolean }) {
  const approved = preview.approved_budget;
  const over = approved ? preview.budget_forecast > approved : false;
  const body = (
    <div className="mt-2 space-y-3 text-[12.5px] text-ink">
      <section>
        <p className="font-semibold">{preview.venue}</p>
        {preview.venue_detail && <p className="text-muted">{preview.venue_detail}</p>}
      </section>

      <section>
        <p className="mb-1 font-semibold">Budget</p>
        <p className={clsx("mb-1.5", over ? "text-danger" : "text-muted")}>
          Forecast {money(preview.budget_forecast)}
          {approved ? ` of ${money(approved)} approved` : ""}
          {over ? " · over budget" : ""}
        </p>
        <ul className="space-y-0.5">
          {preview.budget_lines.map((line) => (
            <li key={line.category} className="flex justify-between gap-3">
              <span>{line.category}</span>
              <span className="tabular-nums text-muted">{money(line.amount)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <p className="mb-1 font-semibold">Agenda</p>
        <ul className="space-y-0.5">
          {preview.agenda.map((item) => (
            <li key={`${item.time}-${item.activity}`} className="flex gap-3">
              <span className="w-20 shrink-0 tabular-nums text-muted">{item.time}</span>
              <span>
                {item.activity} <span className="text-muted">· {item.owner}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      {preview.communications && preview.communications.channels.length > 0 && (
        <section>
          <p className="mb-1 font-semibold">Guest communication</p>
          <p className="text-muted">{preview.communications.channels.join(", ")}</p>
          {preview.communications.checkpoints.length > 0 && <p className="text-muted">Sends: {preview.communications.checkpoints.join(" → ")} · each waits for your approval</p>}
        </section>
      )}

      {preview.open_issues && preview.open_issues.length > 0 && (
        <section className="rounded-md border border-danger/25 bg-danger/[0.04] px-2.5 py-2">
          <p className="mb-1 font-semibold">Still open from the review</p>
          <ul className="list-disc space-y-0.5 pl-4 text-muted">
            {preview.open_issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </section>
      )}

      {preview.caveats && preview.caveats.length > 0 && (
        <section className="rounded-md border border-warn/30 bg-warn/5 px-2.5 py-2">
          <p className="mb-1 font-semibold">To confirm before booking</p>
          <ul className="list-disc space-y-0.5 pl-4 text-muted">
            {preview.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <p className="mb-1 font-semibold">Risks</p>
        <ul className="space-y-1">
          {preview.risks.map((risk) => (
            <li key={risk.title}>
              <span className="font-medium">{risk.title}</span> <span className="text-muted">({risk.level})</span>
              <p className="text-muted">{risk.recommended_action}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );

  if (compact) {
    return (
      <details className="mt-2 rounded-lg border border-border bg-surface px-3 py-2">
        <summary className="cursor-pointer text-[12.5px] font-medium text-ink">Preview the plan</summary>
        {body}
      </details>
    );
  }
  return (
    <div className="mt-2.5 rounded-lg border border-border bg-surface px-3 py-2.5" aria-label="Plan preview">
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">Plan preview</p>
      {body}
    </div>
  );
}
