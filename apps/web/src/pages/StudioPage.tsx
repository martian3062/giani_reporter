import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock3,
  FileAudio,
  Film,
  Link2,
  LockKeyhole,
  PackageCheck,
  Play,
  Save,
  ShieldCheck,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { useDesk } from "../DeskContext";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import type { Episode } from "../types";

const wordCount = (value: string) =>
  value.trim() ? value.trim().split(/\s+/).length : 0;

const isOneSentence = (value: string) => {
  const clean = value.trim();
  if (!clean) return false;
  const boundaries = clean.match(/[.!?]+(?=\s|$)/g) ?? [];
  return boundaries.length <= 1;
};

const runtimeLabel = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

export function StudioPage() {
  const {
    activeEpisode,
    activeEpisodeId,
    episodes,
    stories,
    overview,
    jobs,
    voiceArtifacts,
    setActiveEpisodeId,
    createOrLoadEpisode,
    updateEpisodeLocal,
    saveEpisode,
    generateDraft,
    toggleCompliance,
    approveEpisode,
    generateVoice,
    startRender,
    buildPublishPackage,
    notify,
  } = useDesk();
  const [angle, setAngle] = useState(activeEpisode?.angle ?? "");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setAngle(activeEpisode?.angle ?? "");
  }, [activeEpisode?.angle, activeEpisode?.id]);

  const selectedStories = useMemo(
    () => stories.filter((story) => story.selected).sort((a, b) => b.score - a.score),
    [stories],
  );

  const currentJob = useMemo(
    () =>
      jobs.find(
        (job) =>
          job.episode_id === activeEpisode?.id &&
          (job.status === "running" || job.status === "queued"),
      ) ??
      jobs.find((job) => job.episode_id === activeEpisode?.id),
    [activeEpisode?.id, jobs],
  );
  const currentVoice = activeEpisode
    ? voiceArtifacts[activeEpisode.id]
    : undefined;

  const angleValid = angle.trim().length >= 12 && isOneSentence(angle);
  const words = activeEpisode?.word_count ?? 0;
  const runtime = activeEpisode?.runtime_seconds ?? 0;
  const wordsOkay = words >= 210 && words <= 225;
  const runtimeOkay = runtime > 0 && runtime <= 90;
  const allGatesPassed =
    Boolean(activeEpisode?.compliance.length) &&
    activeEpisode?.compliance.every((gate) => gate.passed);

  const run = async (
    key: string,
    action: () => Promise<{ ok: boolean; message?: string }>,
  ) => {
    setBusy(key);
    const result = await action();
    setBusy(null);
    if (!result.ok && result.message) notify(result.message, "error");
  };

  const updateSection = (key: string, text: string) => {
    if (!activeEpisode) return;
    updateEpisodeLocal({
      sections: activeEpisode.sections.map((section) =>
        section.key === key ? { ...section, text } : section,
      ),
    });
  };

  const updateOverlay = (id: string, text: string) => {
    if (!activeEpisode) return;
    updateEpisodeLocal({
      overlays: activeEpisode.overlays.map((overlay) =>
        overlay.id === id ? { ...overlay, text } : overlay,
      ),
    });
  };

  const workflowSteps = [
    {
      label: "Rundown",
      done: overview.selected_count === 3,
      active: overview.selected_count !== 3,
    },
    {
      label: "Script",
      done: Boolean(activeEpisode?.sections.length),
      active: overview.selected_count === 3 && !activeEpisode?.sections.length,
    },
    {
      label: "Approve",
      done: activeEpisode?.status === "approved" || activeEpisode?.status === "packaged",
      active: Boolean(activeEpisode?.sections.length) && !allGatesPassed,
    },
    {
      label: "Voice",
      done: Boolean(currentVoice),
      active: Boolean(activeEpisode?.script) && !currentVoice,
    },
    {
      label: "Render",
      done: currentJob?.status === "complete",
      active:
        Boolean(activeEpisode?.script) &&
        currentJob?.status !== "complete",
    },
    {
      label: "Package",
      done: activeEpisode?.status === "packaged",
      active: activeEpisode?.status === "approved",
    },
  ];

  return (
    <div className="page-stack studio-page">
      <PageHeader
        eyebrow="Production studio / Daily bulletin"
        title="Make the signal yours."
        description="The angle is human. The structure is assisted. Every final word stays editable."
        action={
          <div className="studio-header-actions">
            {activeEpisode ? <StatusChip status={activeEpisode.status} /> : null}
            <button
              type="button"
              className="button button-secondary"
              onClick={() => void run("save", () => saveEpisode({ angle }))}
              disabled={busy === "save" || !activeEpisode}
            >
              <Save size={17} />
              {busy === "save" ? "Saving…" : "Save draft"}
            </button>
          </div>
        }
      />

      <ol className="workflow-stepper" aria-label="Production workflow">
        {workflowSteps.map((step, index) => (
          <li
            key={step.label}
            className={`${step.done ? "done" : ""} ${step.active ? "active" : ""}`}
          >
            <span>{step.done ? <Check size={15} /> : index + 1}</span>
            <strong>{step.label}</strong>
            {index < workflowSteps.length - 1 ? <ChevronRight size={15} /> : null}
          </li>
        ))}
      </ol>

      <section className="angle-card">
        <div className="angle-card-number">01</div>
        <div className="angle-card-copy">
          <p className="eyebrow">Non-delegable editorial input</p>
          <h2>What is the one thing this edition should land?</h2>
          <p>
            Write one sentence that connects the stories. The script will not generate
            without it.
          </p>
        </div>
        <div className="angle-field-wrap">
          <label htmlFor="episode-angle">One-sentence angle</label>
          <textarea
            id="episode-angle"
            rows={3}
            value={angle}
            aria-describedby="angle-help"
            aria-invalid={Boolean(angle) && !angleValid}
            placeholder="Example: The competitive edge is shifting from model size to the reliability of the whole system."
            onChange={(event) => setAngle(event.target.value)}
          />
          <div id="angle-help" className="field-help">
            <span className={angleValid ? "valid" : ""}>
              {angleValid ? <CheckCircle2 size={14} /> : <Circle size={14} />}
              One sentence · {wordCount(angle)} words
            </span>
            <span>{angle.length} / 220</span>
          </div>
        </div>
        <div className="angle-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={() =>
              void run("load", async () => {
                if (!angleValid) {
                  return {
                    ok: false,
                    message: "Write one clear sentence for the editorial angle.",
                  };
                }
                return createOrLoadEpisode(angle);
              })
            }
            disabled={busy === "load"}
          >
            {busy === "load" ? "Opening…" : "Create / load episode"}
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={() =>
              void run("draft", async () => {
                if (!angleValid) {
                  return {
                    ok: false,
                    message: "The angle must be one complete sentence.",
                  };
                }
                return generateDraft(angle);
              })
            }
            disabled={busy === "draft"}
          >
            <WandSparkles size={17} />
            {busy === "draft" ? "Building draft…" : "Generate structured draft"}
          </button>
        </div>
      </section>

      <section className="source-strip" aria-label="Selected source strip">
        <div className="source-strip-label">
          <Link2 size={17} />
          <span>SOURCE STRIP</span>
        </div>
        {selectedStories.map((story, index) => (
          <a
            key={story.id}
            href={story.url}
            target="_blank"
            rel="noreferrer"
            title={story.title}
          >
            <b>{String(index + 1).padStart(2, "0")}</b>
            <span>
              {story.source}
              {story.is_demo ? " / DEMO" : ""}
            </span>
          </a>
        ))}
        {selectedStories.length !== 3 ? (
          <Link className="source-strip-warning" to="/research">
            Select exactly 3 stories <ArrowRight size={14} />
          </Link>
        ) : null}
      </section>

      <div className="studio-workspace">
        <section className="script-column">
          <div className="panel script-panel">
            <div className="panel-header sticky-panel-header">
              <div>
                <p className="eyebrow">Broadcast copy</p>
                <h2>Structured script</h2>
              </div>
              <div className="episode-picker">
                <label htmlFor="episode-picker">Episode</label>
                <select
                  id="episode-picker"
                  value={activeEpisodeId ?? ""}
                  onChange={(event) => setActiveEpisodeId(event.target.value)}
                >
                  {episodes.map((episode) => (
                    <option key={episode.id} value={episode.id}>
                      {episode.date} · {episode.title || "Untitled"}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {activeEpisode?.sections.length ? (
              <div className="script-sections">
                {activeEpisode.sections.map((section, index) => {
                  const sectionWords = wordCount(section.text);
                  const isTake = section.key === "take";
                  return (
                    <article
                      className={`script-section ${isTake ? "take-section" : ""}`}
                      key={section.key}
                    >
                      <div className="section-label">
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <div>
                          <label htmlFor={`section-${section.key}`}>{section.label}</label>
                          {isTake ? <small>Original editorial argument</small> : null}
                        </div>
                        <strong
                          className={
                            section.target_words &&
                            Math.abs(sectionWords - section.target_words) <= 8
                              ? "count-good"
                              : ""
                          }
                        >
                          {sectionWords}
                          {section.target_words ? ` / ${section.target_words}w` : "w"}
                        </strong>
                      </div>
                      <textarea
                        id={`section-${section.key}`}
                        value={section.text}
                        rows={Math.max(2, Math.ceil(section.text.length / 78))}
                        onChange={(event) =>
                          updateSection(section.key, event.target.value)
                        }
                      />
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="empty-script">
                <Sparkles size={32} />
                <h3>The copy desk is waiting.</h3>
                <p>
                  Lock three stories, write the angle above, then generate a structured
                  starting draft.
                </p>
                <Link className="text-link" to="/research">
                  Check rundown <ArrowRight size={15} />
                </Link>
              </div>
            )}
          </div>

          {activeEpisode?.sections.length ? (
            <>
              <section className="panel metadata-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Publish metadata</p>
                    <h2>Headline & description</h2>
                  </div>
                  <span className={activeEpisode.title.length <= 60 ? "count-good" : ""}>
                    {activeEpisode.title.length} / 60
                  </span>
                </div>
                <label className="field">
                  <span>Video title</span>
                  <input
                    value={activeEpisode.title}
                    onChange={(event) =>
                      updateEpisodeLocal({ title: event.target.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Description</span>
                  <textarea
                    rows={5}
                    value={activeEpisode.description}
                    onChange={(event) =>
                      updateEpisodeLocal({ description: event.target.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Hashtags</span>
                  <input
                    value={activeEpisode.hashtags.join(" ")}
                    onChange={(event) =>
                      updateEpisodeLocal({
                        hashtags: event.target.value
                          .split(/\s+/)
                          .filter(Boolean)
                          .slice(0, 8),
                      })
                    }
                  />
                </label>
              </section>

              <section className="panel timeline-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Visual rhythm</p>
                    <h2>B-roll cue timeline</h2>
                  </div>
                  <span>
                    {activeEpisode.cues.length} cuts · {runtimeLabel(runtime)} bed
                  </span>
                </div>
                <div className="timeline-ruler" aria-label="B-roll timeline">
                  {[0, 15, 30, 45, 60, 75, 90].map((second) => (
                    <span key={second} style={{ left: `${(second / 90) * 100}%` }}>
                      {second}s
                    </span>
                  ))}
                  {activeEpisode.cues.map((cue) => (
                    <button
                      type="button"
                      key={cue.id}
                      className="timeline-cue"
                      style={{
                        left: `${Math.min(96, (cue.at_seconds / 90) * 100)}%`,
                        width: `${Math.max(4, (cue.duration_seconds / 90) * 100)}%`,
                      }}
                      title={`${cue.at_seconds}s · Slot ${cue.slot}: ${cue.label}`}
                      onClick={() =>
                        notify(
                          `${cue.at_seconds}s — B-roll ${String(cue.slot).padStart(2, "0")}: ${cue.label}`,
                        )
                      }
                    >
                      {String(cue.slot).padStart(2, "0")}
                    </button>
                  ))}
                </div>
                <div className="cue-list">
                  {activeEpisode.cues.map((cue) => (
                    <div key={cue.id}>
                      <time>{runtimeLabel(cue.at_seconds)}</time>
                      <strong>#{String(cue.slot).padStart(2, "0")}</strong>
                      <span>{cue.label}</span>
                      <small>{cue.duration_seconds}s</small>
                    </div>
                  ))}
                </div>
              </section>

              <section className="panel overlay-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">On-screen text</p>
                    <h2>Overlay stack</h2>
                  </div>
                  <span>Keep it short. Keep it legible.</span>
                </div>
                <div className="overlay-list">
                  {activeEpisode.overlays.map((overlay, index) => (
                    <label key={overlay.id}>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <time>{runtimeLabel(overlay.at_seconds)}</time>
                      <input
                        value={overlay.text}
                        onChange={(event) =>
                          updateOverlay(overlay.id, event.target.value.toUpperCase())
                        }
                        maxLength={42}
                      />
                      <small>{overlay.text.length}/42</small>
                    </label>
                  ))}
                </div>
              </section>
            </>
          ) : null}
        </section>

        <aside className="review-column">
          <section className="panel runtime-card">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Read check</p>
                <h2>Broadcast fit</h2>
              </div>
              <Clock3 size={20} />
            </div>
            <div className="runtime-display">
              <div>
                <strong>{words}</strong>
                <span>WORDS</span>
              </div>
              <i />
              <div>
                <strong>{runtimeLabel(runtime)}</strong>
                <span>EST. RUN</span>
              </div>
            </div>
            <div className="metric-checks">
              <p className={wordsOkay ? "passed" : ""}>
                {wordsOkay ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                Daily target: 210–225 words
              </p>
              <p className={runtimeOkay ? "passed" : ""}>
                {runtimeOkay ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                Vertical runtime: 90 seconds max
              </p>
              <p className={angleValid ? "passed" : ""}>
                {angleValid ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                One-sentence editorial angle
              </p>
            </div>
          </section>

          <section className="panel compliance-card">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Human gate</p>
                <h2>Compliance</h2>
              </div>
              <ShieldCheck size={21} />
            </div>
            <p className="panel-intro">
              Every check must be a deliberate producer action. Nothing is auto-passed.
            </p>
            <div className="gate-list">
              {(activeEpisode?.compliance ?? []).map((gate) => (
                <label className={gate.passed ? "passed" : ""} key={gate.id}>
                  <input
                    type="checkbox"
                    checked={gate.passed}
                    onChange={() => void toggleCompliance(gate.id)}
                  />
                  <span className="custom-check">
                    <Check size={14} />
                  </span>
                  <span>{gate.label}</span>
                </label>
              ))}
              {!activeEpisode ? (
                <p className="muted-copy">Open an episode to load its gates.</p>
              ) : null}
            </div>
            <div className="gate-progress">
              <span>
                {activeEpisode?.compliance.filter((gate) => gate.passed).length ?? 0} /{" "}
                {activeEpisode?.compliance.length ?? 11} passed
              </span>
              <div>
                <i
                  style={{
                    width: `${
                      activeEpisode?.compliance.length
                        ? (activeEpisode.compliance.filter((gate) => gate.passed).length /
                            activeEpisode.compliance.length) *
                          100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>
          </section>

          <section className="production-actions">
            <p className="eyebrow">Production controls</p>
            <button
              type="button"
              className="production-button"
              onClick={() => void run("approve", approveEpisode)}
              disabled={busy === "approve"}
            >
              <span>
                <LockKeyhole size={19} />
              </span>
              <div>
                <strong>{busy === "approve" ? "Approving…" : "Approve editorial"}</strong>
                <small>Requires all compliance gates</small>
              </div>
              <ChevronRight size={17} />
            </button>
            <button
              type="button"
              className="production-button"
              onClick={() => void run("voice", generateVoice)}
              disabled={busy === "voice"}
            >
              <span>
                <FileAudio size={19} />
              </span>
              <div>
                <strong>{busy === "voice" ? "Generating…" : "Generate voice"}</strong>
                <small>ElevenLabs or configured fallback</small>
              </div>
              <ChevronRight size={17} />
            </button>
            <button
              type="button"
              className="production-button coral"
              onClick={() => void run("render", startRender)}
              disabled={busy === "render"}
            >
              <span>
                <Film size={19} />
              </span>
              <div>
                <strong>{busy === "render" ? "Queuing…" : "Start render"}</strong>
                <small>Anchor, B-roll, captions, overlays</small>
              </div>
              <Play size={16} fill="currentColor" />
            </button>
            <button
              type="button"
              className="production-button"
              onClick={() => void run("package", buildPublishPackage)}
              disabled={busy === "package"}
            >
              <span>
                <PackageCheck size={19} />
              </span>
              <div>
                <strong>{busy === "package" ? "Building…" : "Build publish package"}</strong>
                <small>Video, metadata, sources, disclosure</small>
              </div>
              <ChevronRight size={17} />
            </button>
            {currentJob ? (
              <Link className="current-run-link" to="/runs">
                <span>
                  Render {currentJob.progress}% · {currentJob.stage}
                </span>
                <ArrowRight size={15} />
              </Link>
            ) : null}
          </section>
        </aside>
      </div>
    </div>
  );
}
