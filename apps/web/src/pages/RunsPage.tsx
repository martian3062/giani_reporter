import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Film,
  RefreshCw,
  ServerCog,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useDesk } from "../DeskContext";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";

const formatTime = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

export function RunsPage() {
  const { jobs, episodes, mode, pollJobs, notify } = useDesk();
  const [polling, setPolling] = useState(false);

  const activeCount = jobs.filter(
    (job) => job.status === "running" || job.status === "queued",
  ).length;
  const completeCount = jobs.filter((job) => job.status === "complete").length;
  const failedCount = jobs.filter((job) => job.status === "failed").length;

  const sortedJobs = useMemo(
    () =>
      [...jobs].sort((a, b) => {
        const priority = { running: 0, queued: 1, failed: 2, complete: 3 };
        return priority[a.status] - priority[b.status];
      }),
    [jobs],
  );

  useEffect(() => {
    if (!activeCount) return;
    const interval = window.setInterval(() => {
      void pollJobs();
    }, 3_000);
    return () => window.clearInterval(interval);
  }, [activeCount, pollJobs]);

  const handlePoll = async () => {
    setPolling(true);
    await pollJobs();
    setPolling(false);
    notify("Render state refreshed.", "success");
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Render operations"
        title="Watch every frame move."
        description="Active jobs poll automatically. Failures stay visible until the producer resolves them."
        action={
          <button
            type="button"
            className="button button-secondary"
            onClick={() => void handlePoll()}
            disabled={polling}
          >
            <RefreshCw size={17} className={polling ? "spin" : ""} />
            {polling ? "Polling…" : "Poll now"}
          </button>
        }
      />

      {mode === "demo" ? (
        <p className="demo-note">
          <strong>Simulated run state:</strong> local render jobs advance while this page
          is open. No media is actually produced.
        </p>
      ) : null}

      <section className="runs-summary">
        <article>
          <span className="run-summary-icon active">
            <ServerCog size={20} />
          </span>
          <div>
            <strong>{activeCount}</strong>
            <span>Active runs</span>
          </div>
        </article>
        <article>
          <span className="run-summary-icon complete">
            <CheckCircle2 size={20} />
          </span>
          <div>
            <strong>{completeCount}</strong>
            <span>Completed</span>
          </div>
        </article>
        <article>
          <span className="run-summary-icon failed">
            <AlertTriangle size={20} />
          </span>
          <div>
            <strong>{failedCount}</strong>
            <span>Needs attention</span>
          </div>
        </article>
        <article>
          <span className="run-summary-icon neutral">
            <Clock3 size={20} />
          </span>
          <div>
            <strong>03s</strong>
            <span>Polling cadence</span>
          </div>
        </article>
      </section>

      <section className="run-list" aria-label="Render jobs">
        {sortedJobs.map((job) => {
          const episode = episodes.find((item) => item.id === job.episode_id);
          const outputHref = job.output_path
            ? job.output_path.startsWith("/api/")
              ? `${api.baseUrl.replace(/\/api$/, "")}${job.output_path}`
              : job.output_path
            : undefined;
          return (
            <article className={`run-card run-${job.status}`} key={job.id}>
              <div className="run-card-header">
                <div className="run-icon">
                  <Film size={21} />
                </div>
                <div>
                  <p className="eyebrow">
                    {episode?.date ?? "Unknown date"} / {job.id}
                  </p>
                  <h2>{episode?.title || "Untitled episode"}</h2>
                </div>
                <StatusChip status={job.status} />
              </div>

              <div className="run-progress-copy">
                <strong>{job.stage}</strong>
                <span>{Math.round(job.progress)}%</span>
              </div>
              <div
                className="run-progress"
                role="progressbar"
                aria-label={`${episode?.title || "Episode"} render progress`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(job.progress)}
              >
                <i style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} />
              </div>

              <div className="run-details">
                <div>
                  <span>Episode</span>
                  <strong>{job.episode_id}</strong>
                </div>
                <div>
                  <span>Target runtime</span>
                  <strong>{formatTime(episode?.runtime_seconds ?? 0)}</strong>
                </div>
                <div>
                  <span>Output</span>
                  <strong>{job.output_path ? "Available" : "Pending"}</strong>
                </div>
              </div>

              {job.error ? (
                <div className="run-error" role="alert">
                  <AlertTriangle size={17} />
                  <span>{job.error}</span>
                </div>
              ) : null}

              {job.output_path ? (
                <div className="run-output">
                  <code>{job.output_path}</code>
                  <a
                    className="text-link"
                    href={outputHref}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open artifact <ExternalLink size={14} />
                  </a>
                </div>
              ) : null}
            </article>
          );
        })}

        {!jobs.length ? (
          <div className="empty-state">
            <Film size={31} />
            <h2>No render jobs yet</h2>
            <p>Approve a script, generate voice, then start a render in Studio.</p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
