export function toUiPlan(apiPlan, fallbackPlan) {
  return {
    ...fallbackPlan,
    type: apiPlan.plan_type,
    venue: {
      name: apiPlan.venue,
      area: apiPlan.venue_detail,
      status: apiPlan.source === 'azure' ? 'AI generated' : 'Generated'
    },
    budgetLabels: apiPlan.budget_lines.map(line => line.category),
    budgetShares: apiPlan.budget_lines.map(line => line.share_percent),
    reducedShares: apiPlan.budget_lines.map(line => line.share_percent),
    agenda: apiPlan.agenda.map(item => [item.time, item.activity, item.owner]),
    overviewAgenda: apiPlan.agenda.slice(0, 4).map(item => [item.time, item.activity, item.owner]),
    risks: apiPlan.risks.map(risk => ({
      level: risk.level,
      title: risk.title,
      detail: risk.detail,
      resolved: `Action recorded: ${risk.recommended_action}.`
    })),
    activity: apiPlan.activity.map(item => [item.timestamp, item.agent, item.detail, item.agent.charAt(0)]),
    confidence: apiPlan.confidence,
    source: apiPlan.source
  };
}
