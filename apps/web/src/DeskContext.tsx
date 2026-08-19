import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { api } from "./api";
import {
  activeDemoEpisode,
  complianceTemplate,
  demoCues,
  demoOverlays,
  demoSections,
  demoSnapshot,
} from "./demo";
import type {
  DemoSnapshot,
  EditableEpisodePatch,
  Episode,
  OverviewData,
  RenderJob,
  Story,
  ToastMessage,
  VoiceArtifact,
} from "./types";

type ConnectionMode = "connecting" | "live" | "demo";

interface ActionResult {
  ok: boolean;
  message?: string;
  episode?: Episode;
  job?: RenderJob;
}

interface DeskContextValue {
  mode: ConnectionMode;
  loading: boolean;
  stories: Story[];
  episodes: Episode[];
  jobs: RenderJob[];
  voiceArtifacts: Record<string, VoiceArtifact>;
  activeEpisode: Episode | undefined;
  activeEpisodeId: string | undefined;
  overview: OverviewData;
  toasts: ToastMessage[];
  setActiveEpisodeId: (id: string) => void;
  refreshResearch: () => Promise<void>;
  toggleStory: (id: string) => Promise<void>;
  createOrLoadEpisode: (angle: string) => Promise<ActionResult>;
  updateEpisodeLocal: (patch: Partial<Episode>) => void;
  saveEpisode: (patch?: EditableEpisodePatch) => Promise<ActionResult>;
  generateDraft: (angle: string) => Promise<ActionResult>;
  toggleCompliance: (gateId: string) => Promise<void>;
  approveEpisode: () => Promise<ActionResult>;
  generateVoice: () => Promise<ActionResult>;
  startRender: () => Promise<ActionResult>;
  buildPublishPackage: () => Promise<ActionResult>;
  pollJobs: () => Promise<void>;
  dismissToast: (id: number) => void;
  notify: (message: string, tone?: ToastMessage["tone"]) => void;
}

const DeskContext = createContext<DeskContextValue | undefined>(undefined);
const STORAGE_KEY = "giani.signal-desk.demo.v2";

const cloneDemo = (): DemoSnapshot =>
  JSON.parse(JSON.stringify(demoSnapshot)) as DemoSnapshot;

const loadDemo = (): DemoSnapshot => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as DemoSnapshot;
      if (
        Array.isArray(parsed.stories) &&
        Array.isArray(parsed.episodes) &&
        Array.isArray(parsed.jobs) &&
        parsed.voices &&
        typeof parsed.voices === "object"
      ) {
        return parsed;
      }
    }
  } catch {
    // A blocked or malformed localStorage should never block the desk.
  }
  return cloneDemo();
};

const countWords = (value: string) =>
  value.trim() ? value.trim().split(/\s+/).length : 0;

const withMetrics = (episode: Episode): Episode => {
  const script = episode.sections.map((section) => section.text).join("\n\n");
  const wordCount = countWords(script);
  return {
    ...episode,
    script,
    word_count: wordCount,
    runtime_seconds: Math.round((wordCount / 150) * 60),
    updated_at: new Date().toISOString(),
  };
};

const createLocalEpisode = (storyIds: string[], angle: string): Episode => {
  const episode: Episode = {
    ...JSON.parse(JSON.stringify(activeDemoEpisode)),
    id: `ep-local-${Date.now()}`,
    date: new Date().toISOString().slice(0, 10),
    angle,
    story_ids: storyIds,
    sections: [],
    script: "",
    cues: [],
    overlays: [],
    word_count: 0,
    runtime_seconds: 0,
    status: "planning",
    compliance: complianceTemplate.map((gate) => ({ ...gate })),
    updated_at: new Date().toISOString(),
  };
  return episode;
};

export function DeskProvider({ children }: PropsWithChildren) {
  const initialDemo = useRef(loadDemo());
  const [mode, setMode] = useState<ConnectionMode>("connecting");
  const [loading, setLoading] = useState(true);
  const [stories, setStories] = useState<Story[]>(initialDemo.current.stories);
  const [episodes, setEpisodes] = useState<Episode[]>(
    initialDemo.current.episodes,
  );
  const [jobs, setJobs] = useState<RenderJob[]>(initialDemo.current.jobs);
  const [voiceArtifacts, setVoiceArtifacts] = useState<Record<string, VoiceArtifact>>(
    initialDemo.current.voices,
  );
  const [activeEpisodeId, setActiveEpisodeId] = useState<string | undefined>(
    initialDemo.current.episodes[0]?.id,
  );
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const toastId = useRef(0);

  const notify = useCallback(
    (message: string, tone: ToastMessage["tone"] = "info") => {
      const id = ++toastId.current;
      setToasts((current) => [...current, { id, message, tone }].slice(-4));
      window.setTimeout(() => {
        setToasts((current) => current.filter((toast) => toast.id !== id));
      }, 4_000);
    },
    [],
  );

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  useEffect(() => {
    let cancelled = false;

    const connect = async () => {
      const [healthResult, storiesResult, episodesResult, jobsResult] =
        await Promise.allSettled([
          api.health(),
          api.stories(),
          api.episodes(),
          api.renderJobs(),
        ]);

      if (cancelled) return;

      const liveStories =
        storiesResult.status === "fulfilled" ? storiesResult.value : [];
      const liveEpisodes =
        episodesResult.status === "fulfilled" ? episodesResult.value : [];
      const liveJobs =
        jobsResult.status === "fulfilled" ? jobsResult.value : [];

      if (
        healthResult.status === "fulfilled" &&
        (liveStories.length > 0 || liveEpisodes.length > 0)
      ) {
        setMode("live");
        setStories(liveStories);
        setEpisodes(liveEpisodes);
        setActiveEpisodeId(liveEpisodes[0]?.id);
        setJobs(liveJobs);
        setVoiceArtifacts({});
      } else {
        setMode("demo");
      }
      setLoading(false);
    };

    void connect();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (mode !== "demo") return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ stories, episodes, jobs, voices: voiceArtifacts }),
      );
    } catch {
      // Demo mode remains usable when persistence is unavailable.
    }
  }, [episodes, jobs, mode, stories, voiceArtifacts]);

  const selectedStories = useMemo(
    () =>
      stories
        .filter((story) => story.selected)
        .sort((a, b) => b.score - a.score),
    [stories],
  );

  const activeEpisode = useMemo(
    () => episodes.find((episode) => episode.id === activeEpisodeId),
    [activeEpisodeId, episodes],
  );

  useEffect(() => {
    if (mode !== "live" || !activeEpisodeId) return;
    let cancelled = false;
    void api
      .compliance(activeEpisodeId)
      .then((report) => {
        if (cancelled) return;
        setEpisodes((current) =>
          current.map((episode) =>
            episode.id === activeEpisodeId
              ? { ...episode, compliance: report.gates }
              : episode,
          ),
        );
      })
      .catch(() => {
        // The episode response already carries gates; this refresh is best effort.
      });
    return () => {
      cancelled = true;
    };
  }, [activeEpisodeId, mode]);

  const overview = useMemo<OverviewData>(
    () => ({
      stories_reviewed: stories.length,
      selected_count: selectedStories.length,
      minutes_to_air: activeEpisode
        ? Math.max(0, 60 - Math.round(activeEpisode.runtime_seconds / 3))
        : 60,
      completed_today: episodes.filter((episode) => episode.status === "packaged")
        .length,
      selected_stories: selectedStories,
      recent_episodes: [...episodes]
        .sort(
          (a, b) =>
            new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
        )
        .slice(0, 4),
    }),
    [activeEpisode, episodes, selectedStories, stories.length],
  );

  const refreshResearch = useCallback(async () => {
    if (mode === "live") {
      try {
        const fresh = await api.refreshResearch();
        if (fresh.length) setStories(fresh);
        notify(
          fresh.length
            ? `${fresh.length} stories ranked from live sources.`
            : "Refresh finished. No new stories arrived.",
          "success",
        );
        return;
      } catch {
        setMode("demo");
        notify("Live research went offline. Continuing with demo stories.", "error");
      }
    }

    setStories((current) =>
      current
        .map((story, index) => ({
          ...story,
          score: Math.max(50, Math.min(99, story.score + (index % 2 ? -1 : 1))),
        }))
        .sort((a, b) => b.score - a.score),
    );
    notify("Demo shortlist re-ranked locally.", "success");
  }, [mode, notify]);

  const toggleStory = useCallback(
    async (id: string) => {
      const target = stories.find((story) => story.id === id);
      if (!target) return;

      const selectedCount = stories.filter((story) => story.selected).length;
      if (!target.selected && selectedCount >= 3) {
        notify("The rundown is full. Deselect one story before adding another.", "error");
        return;
      }

      const selected = !target.selected;
      setStories((current) =>
        current.map((story) => (story.id === id ? { ...story, selected } : story)),
      );

      if (mode === "live") {
        try {
          const updated = await api.selectStory(id, selected);
          if (updated?.id) {
            setStories((current) =>
              current.map((story) => (story.id === id ? updated : story)),
            );
          }
        } catch {
          notify("Selection saved locally; the API did not respond.", "error");
          return;
        }
      }
      notify(selected ? "Story added to today’s rundown." : "Story removed.", "success");
    },
    [mode, notify, stories],
  );

  const replaceEpisode = useCallback((next: Episode) => {
    setEpisodes((current) => {
      const exists = current.some((episode) => episode.id === next.id);
      return exists
        ? current.map((episode) => (episode.id === next.id ? next : episode))
        : [next, ...current];
    });
    setActiveEpisodeId(next.id);
  }, []);

  const createOrLoadEpisode = useCallback(
    async (angle: string): Promise<ActionResult> => {
      const cleanAngle = angle.trim();
      if (!cleanAngle) {
        return { ok: false, message: "Write the one-sentence angle first." };
      }
      if (selectedStories.length !== 3) {
        return { ok: false, message: "Select exactly three stories in Research." };
      }

      const today = new Date().toISOString().slice(0, 10);
      const existing = episodes.find(
        (episode) => episode.date === today && episode.kind === "daily",
      );
      const storyIds = selectedStories.map((story) => story.id);

      if (mode === "live") {
        try {
          const next = existing
            ? await api.patchEpisode(existing.id, {
                angle: cleanAngle,
                story_ids: storyIds,
              })
            : await api.createEpisode({
                kind: "daily",
                date: today,
                angle: cleanAngle,
                story_ids: storyIds,
              });
          replaceEpisode(next);
          notify(existing ? "Today’s episode loaded." : "Episode created.", "success");
          return { ok: true, episode: next };
        } catch {
          notify("The API did not respond. A local episode was opened.", "error");
        }
      }

      const next = existing
        ? {
            ...existing,
            angle: cleanAngle,
            story_ids: storyIds,
            updated_at: new Date().toISOString(),
          }
        : createLocalEpisode(storyIds, cleanAngle);
      replaceEpisode(next);
      notify(existing ? "Demo episode loaded." : "Local demo episode created.", "success");
      return { ok: true, episode: next };
    },
    [episodes, mode, notify, replaceEpisode, selectedStories],
  );

  const updateEpisodeLocal = useCallback(
    (patch: Partial<Episode>) => {
      if (!activeEpisodeId) return;
      setEpisodes((current) =>
        current.map((episode) => {
          if (episode.id !== activeEpisodeId) return episode;
          const next = { ...episode, ...patch };
          return patch.sections ? withMetrics(next) : next;
        }),
      );
    },
    [activeEpisodeId],
  );

  const saveEpisode = useCallback(
    async (patch: EditableEpisodePatch = {}): Promise<ActionResult> => {
      if (!activeEpisode) {
        return { ok: false, message: "Open an episode before saving." };
      }
      const next = withMetrics({ ...activeEpisode, ...patch });
      replaceEpisode(next);

      if (mode === "live") {
        try {
          const saved = await api.patchEpisode(activeEpisode.id, {
            angle: next.angle,
            story_ids: next.story_ids,
            sections: next.sections,
            title: next.title,
            description: next.description,
            hashtags: next.hashtags,
            overlays: next.overlays,
            cues: next.cues,
          });
          replaceEpisode(saved);
          notify("Editorial changes saved.", "success");
          return { ok: true, episode: saved };
        } catch {
          notify("Saved locally; the API did not respond.", "error");
          return { ok: true, episode: next };
        }
      }
      notify("Demo draft saved in this browser.", "success");
      return { ok: true, episode: next };
    },
    [activeEpisode, mode, notify, replaceEpisode],
  );

  const generateDraft = useCallback(
    async (angle: string): Promise<ActionResult> => {
      let episode = activeEpisode;
      if (!episode) {
        const created = await createOrLoadEpisode(angle);
        if (!created.ok || !created.episode) return created;
        episode = created.episode;
      }

      if (!angle.trim()) {
        return { ok: false, message: "The editorial angle is mandatory." };
      }
      if (selectedStories.length !== 3) {
        return { ok: false, message: "A daily bulletin requires exactly three stories." };
      }

      if (mode === "live") {
        try {
          const prepared = await api.patchEpisode(episode.id, {
            angle: angle.trim(),
            story_ids: selectedStories.map((story) => story.id),
          });
          const drafted = await api.draftEpisode(prepared.id);
          replaceEpisode(drafted);
          notify("Structured script generated.", "success");
          return { ok: true, episode: drafted };
        } catch {
          notify("Draft API unavailable. Loaded a clearly marked demo draft.", "error");
        }
      }

      const sections = JSON.parse(JSON.stringify(demoSections)) as Episode["sections"];
      const takeIndex = sections.findIndex((section) => section.key === "take");
      if (takeIndex >= 0) {
        sections[takeIndex] = {
          ...sections[takeIndex],
          text: `Here is the pattern ... ${angle.trim()} Smaller models, cleaner handoffs, and cheaper inference all reward operational discipline. The advantage is not one giant leap. It is fewer broken steps.`,
        };
      }
      const drafted = withMetrics({
        ...episode,
        angle: angle.trim(),
        story_ids: selectedStories.map((story) => story.id),
        sections,
        cues: JSON.parse(JSON.stringify(demoCues)),
        overlays: JSON.parse(JSON.stringify(demoOverlays)),
        title: "AI’s Next Edge Is Operational",
        status: "draft",
        compliance: complianceTemplate.map((gate) => ({ ...gate })),
      });
      replaceEpisode(drafted);
      notify("Demo script generated and ready to edit.", "success");
      return { ok: true, episode: drafted };
    },
    [
      activeEpisode,
      createOrLoadEpisode,
      mode,
      notify,
      replaceEpisode,
      selectedStories,
    ],
  );

  const toggleCompliance = useCallback(
    async (gateId: string) => {
      if (!activeEpisode) return;
      const gate = activeEpisode.compliance.find((item) => item.id === gateId);
      if (!gate) return;
      const passed = !gate.passed;
      updateEpisodeLocal({
        compliance: activeEpisode.compliance.map((item) =>
          item.id === gateId ? { ...item, passed } : item,
        ),
      });

      if (mode === "live") {
        try {
          const report = await api.updateCompliance(
            activeEpisode.id,
            gateId,
            passed,
          );
          updateEpisodeLocal({ compliance: report.gates });
        } catch {
          notify("Gate updated locally; sync is pending.", "error");
          return;
        }
      }
      notify(passed ? "Compliance gate passed." : "Compliance gate reopened.");
    },
    [activeEpisode, mode, notify, updateEpisodeLocal],
  );

  const approveEpisode = useCallback(async (): Promise<ActionResult> => {
    if (!activeEpisode) return { ok: false, message: "Open an episode first." };
    if (!activeEpisode.sections.length) {
      return { ok: false, message: "Generate and review the script first." };
    }
    if (activeEpisode.compliance.some((gate) => !gate.passed)) {
      return { ok: false, message: "Pass every compliance gate before approval." };
    }

    if (mode === "live") {
      try {
        const approved = await api.approveEpisode(activeEpisode.id);
        replaceEpisode(approved);
        notify("Episode approved for production.", "success");
        return { ok: true, episode: approved };
      } catch {
        return {
          ok: false,
          message: "Approval failed. Review the backend validation details and try again.",
        };
      }
    }
    const approved = { ...activeEpisode, status: "approved" as const };
    replaceEpisode(approved);
    notify("Demo episode approved.", "success");
    return { ok: true, episode: approved };
  }, [activeEpisode, mode, notify, replaceEpisode]);

  const generateVoice = useCallback(async (): Promise<ActionResult> => {
    if (!activeEpisode) return { ok: false, message: "Open an episode first." };
    if (!activeEpisode.script.trim()) {
      return { ok: false, message: "Generate and save the script before voice." };
    }

    if (mode === "live") {
      try {
        const artifact = await api.voiceEpisode(activeEpisode.id);
        setVoiceArtifacts((current) => ({
          ...current,
          [activeEpisode.id]: artifact,
        }));
        notify(
          artifact.is_demo
            ? "Demo voice artifact created. Configure ElevenLabs for audio."
            : "Voice track generated.",
          artifact.is_demo ? "info" : "success",
        );
        return { ok: true, episode: activeEpisode };
      } catch {
        return { ok: false, message: "Voice generation failed. No artifact was recorded." };
      }
    }
    const artifact: VoiceArtifact = {
      episode_id: activeEpisode.id,
      provider: "demo",
      output_path: `/voice/${activeEpisode.id}.demo.txt`,
      is_demo: true,
      error: "",
    };
    setVoiceArtifacts((current) => ({
      ...current,
      [activeEpisode.id]: artifact,
    }));
    notify("Demo voice artifact recorded locally; it is not audio.", "success");
    return { ok: true, episode: activeEpisode };
  }, [activeEpisode, mode, notify]);

  const startRender = useCallback(async (): Promise<ActionResult> => {
    if (!activeEpisode) return { ok: false, message: "Open an episode first." };
    if (!activeEpisode.script.trim()) {
      return { ok: false, message: "Draft the script before creating a render job." };
    }

    if (mode === "live") {
      try {
        const job = await api.renderEpisode(activeEpisode.id);
        setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
        notify("Render queued. Track it in Runs.", "success");
        return { ok: true, job };
      } catch {
        return { ok: false, message: "The render job could not be queued." };
      }
    }

    const job: RenderJob = {
      id: `render-local-${Date.now()}`,
      episode_id: activeEpisode.id,
      status: "running",
      progress: 8,
      stage: "Preparing anchor and voice",
      output_path: null,
      error: null,
    };
    setJobs((current) => [job, ...current]);
    notify("Demo render started. Progress is simulated locally.", "success");
    return { ok: true, job };
  }, [activeEpisode, mode, notify]);

  const pollJobs = useCallback(async () => {
    if (mode === "live") {
      const updates = await Promise.allSettled(
        jobs
          .filter((job) => job.status === "queued" || job.status === "running")
          .map((job) => api.renderJob(job.id)),
      );
      const resolved = updates
        .filter(
          (result): result is PromiseFulfilledResult<RenderJob> =>
            result.status === "fulfilled",
        )
        .map((result) => result.value);
      if (resolved.length) {
        setJobs((current) =>
          current.map(
            (job) => resolved.find((result) => result.id === job.id) ?? job,
          ),
        );
      }
      return;
    }

    setJobs((current) =>
      current.map((job) => {
        if (job.status !== "running" && job.status !== "queued") return job;
        const progress = Math.min(100, job.progress + 7);
        const stage =
          progress < 28
            ? "Preparing anchor and voice"
            : progress < 52
              ? "Lip-sync pass"
              : progress < 78
                ? "Compositing B-roll"
                : progress < 100
                  ? "Captions and quality control"
                  : "Delivery package ready";
        return {
          ...job,
          progress,
          stage,
          status: progress >= 100 ? "complete" : "running",
          output_path:
            progress >= 100 ? `/renders/${job.episode_id}/final.mp4` : null,
        };
      }),
    );

  }, [jobs, mode]);

  const hasActiveJobs = jobs.some(
    (job) => job.status === "queued" || job.status === "running",
  );

  useEffect(() => {
    if (!hasActiveJobs) return;
    const interval = window.setInterval(() => {
      void pollJobs();
    }, 1_500);
    return () => window.clearInterval(interval);
  }, [hasActiveJobs, pollJobs]);

  const buildPublishPackage = useCallback(async (): Promise<ActionResult> => {
    if (!activeEpisode) return { ok: false, message: "Open an episode first." };
    if (activeEpisode.status !== "approved") {
      return { ok: false, message: "Approve the episode before packaging." };
    }
    if (activeEpisode.compliance.some((gate) => !gate.passed)) {
      return { ok: false, message: "Pass every compliance gate before packaging." };
    }

    if (mode === "live") {
      try {
        await api.publishPackage(activeEpisode.id);
      } catch {
        return { ok: false, message: "The publish package could not be created." };
      }
    }
    const packaged = { ...activeEpisode, status: "packaged" as const };
    replaceEpisode(packaged);
    notify("Publish package is ready with metadata and disclosures.", "success");
    return { ok: true, episode: packaged };
  }, [activeEpisode, mode, notify, replaceEpisode]);

  const value = useMemo<DeskContextValue>(
    () => ({
      mode,
      loading,
      stories,
      episodes,
      jobs,
      voiceArtifacts,
      activeEpisode,
      activeEpisodeId,
      overview,
      toasts,
      setActiveEpisodeId,
      refreshResearch,
      toggleStory,
      createOrLoadEpisode,
      updateEpisodeLocal,
      saveEpisode,
      generateDraft,
      toggleCompliance,
      approveEpisode,
      generateVoice,
      startRender,
      buildPublishPackage,
      pollJobs,
      dismissToast,
      notify,
    }),
    [
      activeEpisode,
      activeEpisodeId,
      approveEpisode,
      buildPublishPackage,
      createOrLoadEpisode,
      dismissToast,
      episodes,
      generateDraft,
      generateVoice,
      jobs,
      loading,
      mode,
      notify,
      overview,
      pollJobs,
      refreshResearch,
      saveEpisode,
      startRender,
      stories,
      toasts,
      toggleCompliance,
      toggleStory,
      updateEpisodeLocal,
      voiceArtifacts,
    ],
  );

  return <DeskContext.Provider value={value}>{children}</DeskContext.Provider>;
}

export const useDesk = () => {
  const context = useContext(DeskContext);
  if (!context) {
    throw new Error("useDesk must be used inside DeskProvider");
  }
  return context;
};
