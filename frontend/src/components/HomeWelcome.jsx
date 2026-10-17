import './homeWelcome.css';

export function HomeWelcome({ onStartPlanning }) {
  return <section className="landing-page view active">
    <section className="home-welcome">
      <div className="welcome-copy">
        <p className="eyebrow">AUTONOMOUS EVENT PLANNING</p>
        <h1>Events with a plan behind every detail.</h1>
        <p>EventPilot turns a short brief into a coordinated event plan. Your AI planning team balances venue, budget, schedule, guest communication, and operational risks in one reviewable workspace.</p>
        <div className="landing-actions"><button className="button primary" onClick={onStartPlanning}>Plan an event <span>→</span></button><button className="landing-text-action" onClick={onStartPlanning}>Talk to the planner</button></div>
        <div className="welcome-signals"><span><b>6</b> planning disciplines</span><span><b>1</b> reviewed event blueprint</span><span><b>12 hr</b> event-day schedule</span></div>
      </div>
      <div className="welcome-visual" role="img" aria-label="Event planning workspace illustration placeholder">
      <div className="visual-grid" />
        <div className="visual-board"><span className="visual-label">EVENT BLUEPRINT</span><div className="visual-line wide" /><div className="visual-line" /><div className="visual-line short" /><div className="visual-timeline"><i /><i /><i /><i /></div></div>
        <div className="visual-calendar"><b>21</b><span>EVENT DAY</span></div><div className="visual-pin" /><div className="visual-note">Venue<br />Guest flow<br />Budget</div>
      </div>
    </section>
    <section className="landing-route" aria-label="Planning workflow"><p className="eyebrow">FROM BRIEF TO BLUEPRINT</p><div><article><span>01</span><h2>Share the event brief</h2><p>Answer a few focused questions with the planning assistant.</p></article><article><span>02</span><h2>Review agent decisions</h2><p>See recommendations across logistics, finance, schedule, and risks.</p></article><article><span>03</span><h2>Approve with confidence</h2><p>Record decisions and export the final event blueprint.</p></article></div></section>
  </section>;
}
