/**
 * Shown on the overview and plan pages when an event has no approved plan yet.
 * It replaces the built-in sample plan, so nothing made-up appears as this event's plan.
 */
export default function NoPlanYet({ eventName, runStatus, onGenerate, onReviewRun }) {
  const readyForDecision = runStatus === 'awaiting_input';
  return (
    <section className="no-plan-yet" aria-label="No plan yet">
      <p className="eyebrow">{readyForDecision ? 'Ready for your decision' : 'No approved plan yet'}</p>
      <h2>{eventName}</h2>
      <p>
        {readyForDecision
          ? 'The planning team has built the plan. Review it, then approve it or send it back with changes.'
          : 'Generate the plan to see the venue, budget, agenda and risks for this event.'}
      </p>
      <button type="button" className="button primary" onClick={readyForDecision ? onReviewRun : onGenerate}>
        {readyForDecision ? 'Review the plan' : 'Generate plan'}
      </button>
    </section>
  );
}
