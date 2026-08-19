import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileStack,
  Gauge,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router";
import { useDesk } from "../DeskContext";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";

const relativeTime = (iso: string) => {
  const deltaMinutes = Math.max(
    1,
    Math.round((Date.now() - new Date(iso).getTime()) / 60_000),
  );
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;
  const hours = Math.round(deltaMinutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
};

const formatDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
  });

export function OverviewPage() {
  const { overview, activeEpisode, loading, mode } = useDesk();
  const hasDemoContent = overview.selected_stories.some((story) => story.is_demo);
  const targetWords =
    activeEpisode?.kind === "deep_dive" ? "900–1,100" : "210–225";
  const targetRuntime =
    activeEpisode?.kind === "deep_dive" ? "6–7 min" : "≤ 90 sec";

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Editorial control room"
        title="Good evening. The desk is live."
        description="One human angle. Three verified stories. One publish-ready signal."
        action={
          <Link className="button button-secondary" to="/research">
            Review shortlist <ArrowRight size={17} />
          </Link>
        }
      />

      {loading ? (
        <div className="connection-line" role="status">
          <span className="pulse-dot" />
          Looking for the newsroom API…
        </div>
      ) : mode === "demo" || hasDemoContent ? (
        <div className="demo-banner">
          <Sparkles size={18} aria-hidden="true" />
          <div>
            <strong>{mode === "live" ? "Demo sources active" : "Demo desk active"}</strong>
            <span>
              Every sample headline is fictional and labeled.
              {mode === "demo" ? " Your edits stay in this browser." : ""}
            </span>
          </div>
          <Link to="/settings">Connection details</Link>
        </div>
      ) : null}

      <section className="stat-grid" aria-label="Today’s production summary">
        <article className="stat-card stat-dark">
          <span className="stat-icon">
            <FileStack size={20} />
          </span>
          <p>Stories reviewed</p>
          <strong>{String(overview.stories_reviewed).padStart(2, "0")}</strong>
          <small>ranked by editorial signal</small>
        </article>
        <article className="stat-card">
          <span className="stat-icon accent-blue">
            <CheckCircle2 size={20} />
          </span>
          <p>Rundown locked</p>
          <strong>{overview.selected_count}<i>/ 3</i></strong>
          <small>
            {overview.selected_count === 3 ? "ready for scripting" : "selection required"}
          </small>
        </article>
        <article className="stat-card">
          <span className="stat-icon accent-coral">
            <Clock3 size={20} />
          </span>
          <p>Est. desk time</p>
          <strong>{overview.minutes_to_air}<i> min</i></strong>
          <small>to a reviewed package</small>
        </article>
        <article className="stat-card">
          <span className="stat-icon accent-yellow">
            <Gauge size={20} />
          </span>
          <p>Runtime target</p>
          <strong>{targetRuntime}</strong>
          <small>{targetWords} spoken words</small>
        </article>
      </section>

      <section className="overview-grid">
        <article className="panel selected-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Today’s rundown</p>
              <h2>Selected signals</h2>
            </div>
            <span className="fraction-label">{overview.selected_count} / 3</span>
          </div>
          <div className="selected-story-list">
            {overview.selected_stories.length ? (
              overview.selected_stories.map((story, index) => (
                <article className="selected-story" key={story.id}>
                  <span className="story-index">{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <div className="story-meta">
                      <span>{story.topic}</span>
                      <span>{story.source}</span>
                      {story.is_demo ? <b>DEMO</b> : null}
                    </div>
                    <h3>{story.title}</h3>
                    <p>{story.why_it_matters}</p>
                  </div>
                  <div className="signal-score" aria-label={`Signal score ${story.score}`}>
                    <strong>{story.score}</strong>
                    <span>SIG</span>
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-state compact">
                <p>No stories selected yet.</p>
                <Link to="/research">Open the research desk</Link>
              </div>
            )}
          </div>
          <div className="panel-footer">
            <Link className="text-link" to="/research">
              Adjust rundown <ArrowRight size={15} />
            </Link>
          </div>
        </article>

        <article className="anchor-card">
          <div className="anchor-visual">
            <img
              src="/anchor/mira-anchor-vertical.png"
              alt="Mira, the GIANI AI news anchor"
            />
            <div className="frame-corner frame-top-left" />
            <div className="frame-corner frame-top-right" />
            <div className="anchor-live-tag">
              <span />
              Canonical frame
            </div>
            <div className="anchor-lower-third">
              <span>GIANI / AI DESK</span>
              <strong>MIRA</strong>
              <small>DAILY SIGNAL</small>
            </div>
          </div>
          <div className="anchor-info">
            <div>
              <p className="eyebrow">On-camera identity</p>
              <h2>Mira</h2>
            </div>
            <span className="asset-ready">
              <CheckCircle2 size={16} />
              Asset ready
            </span>
          </div>
        </article>
      </section>

      <section className="lower-grid">
        <article className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Production clock</p>
              <h2>Today’s pipeline</h2>
            </div>
            {activeEpisode ? <StatusChip status={activeEpisode.status} /> : null}
          </div>
          <ol className="pipeline-list">
            {[
              ["Research", overview.selected_count === 3, "3 stories"],
              ["Angle", Boolean(activeEpisode?.angle), "human input"],
              ["Script", Boolean(activeEpisode?.sections.length), "editorial draft"],
              [
                "Compliance",
                Boolean(activeEpisode?.compliance.every((gate) => gate.passed)),
                "6 gates",
              ],
              [
                "Delivery",
                activeEpisode?.status === "packaged",
                "publish package",
              ],
            ].map(([label, done, note], index) => (
              <li className={done ? "done" : ""} key={String(label)}>
                <span className="pipeline-number">{index + 1}</span>
                <div>
                  <strong>{label}</strong>
                  <small>{note}</small>
                </div>
                {done ? <CheckCircle2 size={18} /> : <span className="pipeline-wait" />}
              </li>
            ))}
          </ol>
          <Link className="button button-primary button-full" to="/studio">
            Continue in Studio <ArrowRight size={17} />
          </Link>
        </article>

        <article className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Archive pulse</p>
              <h2>Recent editions</h2>
            </div>
            <Link className="text-link" to="/runs">
              View runs
            </Link>
          </div>
          <div className="episode-table" role="table" aria-label="Recent episodes">
            {overview.recent_episodes.map((episode) => (
              <div className="episode-row" role="row" key={episode.id}>
                <span className="episode-date" role="cell">
                  {formatDate(episode.date)}
                </span>
                <div role="cell">
                  <strong>{episode.title || "Untitled bulletin"}</strong>
                  <small>
                    {episode.word_count} words · {Math.floor(episode.runtime_seconds / 60)}:
                    {String(episode.runtime_seconds % 60).padStart(2, "0")} run
                  </small>
                </div>
                <StatusChip status={episode.status} />
                <time dateTime={episode.updated_at}>
                  {relativeTime(episode.updated_at)}
                </time>
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  );
}
