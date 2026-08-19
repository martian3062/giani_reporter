import {
  ArrowUpDown,
  Check,
  ExternalLink,
  RefreshCw,
  Search,
  SignalHigh,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useDesk } from "../DeskContext";
import { PageHeader } from "../components/PageHeader";

const timeAgo = (iso: string) => {
  const hours = Math.max(
    0,
    Math.round((Date.now() - new Date(iso).getTime()) / 3_600_000),
  );
  return hours < 1 ? "Just now" : `${hours}h ago`;
};

export function ResearchPage() {
  const { stories, mode, refreshResearch, toggleStory, overview } = useDesk();
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("All");
  const [sortNewest, setSortNewest] = useState(false);
  const hasOnlyDemoStories =
    stories.length > 0 && stories.every((story) => story.is_demo);

  const topics = useMemo(
    () => ["All", ...Array.from(new Set(stories.map((story) => story.topic)))],
    [stories],
  );

  const visibleStories = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return stories
      .filter((story) => topic === "All" || story.topic === topic)
      .filter(
        (story) =>
          !normalized ||
          story.title.toLowerCase().includes(normalized) ||
          story.summary.toLowerCase().includes(normalized) ||
          story.source.toLowerCase().includes(normalized),
      )
      .sort((a, b) =>
        sortNewest
          ? new Date(b.published_at).getTime() - new Date(a.published_at).getTime()
          : b.score - a.score,
      );
  }, [query, sortNewest, stories, topic]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await refreshResearch();
    setRefreshing(false);
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Research desk / 06:30 ingest"
        title="Find the signal."
        description="Ranked source notes only. The desk chooses the stories and authors the angle."
        action={
          <button
            type="button"
            className="button button-primary"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
          >
            <RefreshCw size={17} className={refreshing ? "spin" : ""} />
            {refreshing ? "Refreshing…" : "Refresh sources"}
          </button>
        }
      />

      <div className="research-status-bar">
        <div>
          <SignalHigh size={18} aria-hidden="true" />
          <span>
            Source state:{" "}
            <strong>
              {mode === "live" && !hasOnlyDemoStories ? "LIVE FEED" : "LOCAL DEMO"}
            </strong>
          </span>
        </div>
        <div className={overview.selected_count === 3 ? "selection-ready" : ""}>
          <span>Today’s selection</span>
          <strong>{overview.selected_count} / 3</strong>
          <div className="mini-bars" aria-hidden="true">
            {[0, 1, 2].map((index) => (
              <i key={index} className={index < overview.selected_count ? "filled" : ""} />
            ))}
          </div>
          <Link to="/studio">
            {overview.selected_count === 3 ? "Write angle" : "Need 3 stories"}
          </Link>
        </div>
      </div>

      <section className="research-toolbar" aria-label="Research filters">
        <label className="search-field">
          <Search size={18} aria-hidden="true" />
          <span className="sr-only">Search stories</span>
          <input
            type="search"
            value={query}
            placeholder="Search headlines, sources, or notes"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="topic-filters" aria-label="Filter by topic">
          {topics.map((item) => (
            <button
              type="button"
              key={item}
              className={topic === item ? "filter-pill active" : "filter-pill"}
              onClick={() => setTopic(item)}
              aria-pressed={topic === item}
            >
              {item}
            </button>
          ))}
        </div>
        <button
          className="button button-ghost button-compact"
          type="button"
          onClick={() => setSortNewest((current) => !current)}
          aria-pressed={sortNewest}
        >
          <ArrowUpDown size={16} />
          {sortNewest ? "Newest" : "Top signal"}
        </button>
      </section>

      {mode === "demo" || hasOnlyDemoStories ? (
        <p className="demo-note">
          <strong>Demo dataset:</strong> these are fictional sample headlines, not current
          news.
        </p>
      ) : null}

      <section className="story-card-list" aria-label="Ranked stories">
        {visibleStories.map((story) => {
          const rank = stories
            .slice()
            .sort((a, b) => b.score - a.score)
            .findIndex((item) => item.id === story.id) + 1;
          return (
            <article
              className={`research-card ${story.selected ? "selected" : ""}`}
              key={story.id}
            >
              <div className="rank-column">
                <span>RANK</span>
                <strong>{String(rank).padStart(2, "0")}</strong>
                <div className="score-bar" aria-hidden="true">
                  <i style={{ height: `${story.score}%` }} />
                </div>
              </div>
              <div className="research-card-body">
                <div className="story-meta">
                  <span>{story.topic}</span>
                  <span>{story.source}</span>
                  <time dateTime={story.published_at}>{timeAgo(story.published_at)}</time>
                  {story.is_demo ? <b>DEMO</b> : null}
                </div>
                <h2>{story.title}</h2>
                <p>{story.summary}</p>
                <div className="why-box">
                  <span>WHY IT MATTERS</span>
                  <p>{story.why_it_matters}</p>
                </div>
                <a
                  className="source-link"
                  href={story.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open source note <ExternalLink size={14} />
                </a>
              </div>
              <div className="research-card-actions">
                <div className="signal-score large">
                  <strong>{story.score}</strong>
                  <span>SIGNAL</span>
                </div>
                <button
                  type="button"
                  className={
                    story.selected
                      ? "select-button selected"
                      : "select-button"
                  }
                  aria-pressed={story.selected}
                  onClick={() => void toggleStory(story.id)}
                >
                  {story.selected ? (
                    <>
                      <Check size={17} /> Selected
                    </>
                  ) : (
                    <>
                      <span>+</span> Add to rundown
                    </>
                  )}
                </button>
              </div>
            </article>
          );
        })}
        {!visibleStories.length ? (
          <div className="empty-state">
            <Search size={30} />
            <h2>No stories match this view</h2>
            <p>Clear the search or choose another topic.</p>
            <button
              type="button"
              className="button button-secondary"
              onClick={() => {
                setQuery("");
                setTopic("All");
              }}
            >
              Clear filters
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
