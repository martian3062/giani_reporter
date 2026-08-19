import type {
  BrollCue,
  Capabilities,
  ComplianceGate,
  ComplianceReport,
  EditableEpisodePatch,
  Episode,
  ImageProvider,
  OverviewData,
  Overlay,
  Post,
  PostFormat,
  PostPatchBody,
  PublishPackage,
  PublishPreview,
  RenderJob,
  ScriptSection,
  Story,
  VoiceArtifact,
} from "./types";

const API_URL = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");

export class ApiError extends Error {
  status?: number;
  /** Every reason the backend refused, when it sent a list. */
  blockers: string[];

  constructor(message: string, status?: number, blockers: string[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.blockers = blockers;
  }
}

/**
 * FastAPI puts the operator-facing reason in `detail`. Losing it turns an
 * actionable refusal ("caption is missing the AI disclosure") into a bare
 * status code, so it is unpacked here.
 */
const describeFailure = async (
  response: Response,
): Promise<{ message: string; blockers: string[] }> => {
  const fallback = `Request failed with ${response.status}`;
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { message: fallback, blockers: [] };
  }

  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return { message: detail, blockers: [] };

  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    const list = [record.blockers, record.errors, record.missing].find(
      Array.isArray,
    ) as unknown[] | undefined;
    const blockers = (list ?? []).map(String);
    const message =
      typeof record.message === "string"
        ? record.message
        : blockers[0] ?? fallback;
    return { message, blockers };
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : String(item),
      )
      .filter(Boolean);
    return { message: messages[0] ?? fallback, blockers: messages };
  }

  return { message: fallback, blockers: [] };
};

const request = async <T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 6_000,
): Promise<T> => {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const isFormData =
      typeof FormData !== "undefined" && init?.body instanceof FormData;
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body && !isFormData
          ? { "Content-Type": "application/json" }
          : {}),
        ...init?.headers,
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      const { message, blockers } = await describeFailure(response);
      throw new ApiError(message, response.status, blockers);
    }

    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const message =
      error instanceof DOMException && error.name === "AbortError"
        ? "The API timed out"
        : "The API is unavailable";
    throw new ApiError(message);
  } finally {
    window.clearTimeout(timeout);
  }
};

const asRecord = (value: unknown): Record<string, unknown> | undefined =>
  typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : undefined;

export const unwrapObject = <T>(payload: unknown): T => {
  const record = asRecord(payload);
  if (!record) return payload as T;

  for (const key of ["data", "item", "result", "episode", "job"]) {
    const value = record[key];
    if (value && !Array.isArray(value) && typeof value === "object") {
      return value as T;
    }
  }

  return payload as T;
};

export const unwrapList = <T>(
  payload: unknown,
  domainKeys: string[] = [],
): T[] => {
  if (Array.isArray(payload)) return payload as T[];
  const record = asRecord(payload);
  if (!record) return [];

  for (const key of [...domainKeys, "items", "results", "data"]) {
    if (Array.isArray(record[key])) return record[key] as T[];

    const nested = asRecord(record[key]);
    if (nested) {
      for (const nestedKey of [...domainKeys, "items", "results"]) {
        if (Array.isArray(nested[nestedKey])) return nested[nestedKey] as T[];
      }
    }
  }

  return [];
};

const json = (value: unknown, method = "POST"): RequestInit => ({
  method,
  body: JSON.stringify(value),
});

const sectionOrder: Record<Episode["kind"], string[]> = {
  daily: ["hook", "story_1", "story_2", "story_3", "take", "sign_off"],
  deep_dive: [
    "hook",
    "what_happened",
    "background",
    "mechanism",
    "who_wins_who_loses",
    "take",
    "sign_off",
  ],
};

const sectionMeta: Record<string, { label: string; target_words?: number }> = {
  hook: { label: "Hook", target_words: 12 },
  story_1: { label: "Story 01", target_words: 52 },
  story_2: { label: "Story 02", target_words: 47 },
  story_3: { label: "Story 03", target_words: 42 },
  what_happened: { label: "What happened", target_words: 150 },
  background: { label: "Background", target_words: 250 },
  mechanism: { label: "The mechanism", target_words: 250 },
  who_wins_who_loses: { label: "Who wins / who loses", target_words: 200 },
  take: { label: "The take", target_words: 51 },
  sign_off: { label: "Sign-off", target_words: 8 },
};

export const complianceLabels: Record<string, string> = {
  opinion: "Episode contains a stated opinion or argument",
  take_connects_stories: "The take connects the selected stories",
  format_varied: "Format varies from the previous three editions",
  advice_safe: "No medical, legal, financial, or political advice",
  neutral_anchor: "Anchor uses neutral AI Desk framing",
  figures_sourced: "Every figure is traced to a source",
  no_verify_tags: "No [VERIFY] tags remain",
  sources_linked: "Every source is linked in the description",
  synthetic_disclosure: "Synthetic-content disclosure is queued",
  broll_cadence: "B-roll appears at least every 12 seconds",
  one_upload_today: "This is the only upload scheduled today",
};

const valueRecord = (value: unknown) => asRecord(value) ?? {};
const valueString = (value: unknown, fallback = "") =>
  typeof value === "string" ? value : fallback;
const valueNumber = (value: unknown, fallback = 0) =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

const normalizeSections = (
  kind: Episode["kind"],
  value: unknown,
): ScriptSection[] => {
  if (Array.isArray(value)) return value as ScriptSection[];
  const record = valueRecord(value);
  const knownOrder = sectionOrder[kind];
  const keys = [
    ...knownOrder.filter((key) => key in record),
    ...Object.keys(record).filter((key) => !knownOrder.includes(key)),
  ];
  return keys.map((key) => ({
    key,
    label:
      sectionMeta[key]?.label ??
      key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
    text: valueString(record[key]),
    target_words: sectionMeta[key]?.target_words,
  }));
};

const normalizeCompliance = (value: unknown): ComplianceGate[] => {
  if (Array.isArray(value)) return value as ComplianceGate[];
  return Object.entries(valueRecord(value)).map(([id, passed]) => ({
    id,
    label:
      complianceLabels[id] ??
      id.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
    passed: Boolean(passed),
  }));
};

const normalizeOverlays = (value: unknown): Overlay[] =>
  (Array.isArray(value) ? value : []).map((item, index) => {
    const record = valueRecord(item);
    return {
      id: valueString(record.id, `overlay-${index + 1}`),
      at_seconds: valueNumber(
        record.at_seconds,
        valueNumber(record.timestamp_seconds),
      ),
      text: valueString(record.text),
    };
  });

const normalizeCues = (value: unknown): BrollCue[] =>
  (Array.isArray(value) ? value : []).map((item, index) => {
    const record = valueRecord(item);
    return {
      id: valueString(record.id, `cue-${index + 1}`),
      at_seconds: valueNumber(
        record.at_seconds,
        valueNumber(record.timestamp_seconds),
      ),
      duration_seconds: valueNumber(record.duration_seconds, 5),
      slot: valueNumber(record.slot, valueNumber(record.broll_id, index + 1)),
      label: valueString(record.label, "Reusable library cue"),
    };
  });

export const normalizeEpisode = (payload: unknown): Episode => {
  const record = valueRecord(unwrapObject<unknown>(payload));
  const kind: Episode["kind"] =
    record.kind === "deep_dive" ? "deep_dive" : "daily";
  const status: Episode["status"] = ["planning", "draft", "approved", "packaged"].includes(
    valueString(record.status),
  )
    ? (record.status as Episode["status"])
    : "planning";

  return {
    id: valueString(record.id),
    kind,
    status,
    date: valueString(record.date),
    angle: valueString(record.angle),
    story_ids: Array.isArray(record.story_ids)
      ? record.story_ids.map((id) => String(id))
      : [],
    script: valueString(record.script),
    sections: normalizeSections(kind, record.sections),
    title: valueString(record.title),
    description: valueString(record.description),
    hashtags: Array.isArray(record.hashtags)
      ? record.hashtags.map((hashtag) => String(hashtag))
      : [],
    overlays: normalizeOverlays(record.overlays),
    cues: normalizeCues(record.cues),
    word_count: valueNumber(record.word_count),
    runtime_seconds: valueNumber(record.runtime_seconds),
    compliance: normalizeCompliance(record.compliance),
    updated_at: valueString(record.updated_at),
  };
};

export const serializeEpisodePatch = (
  patch: EditableEpisodePatch,
): Record<string, unknown> => {
  const result: Record<string, unknown> = {};
  const scalarKeys = [
    "date",
    "angle",
    "story_ids",
    "script",
    "title",
    "description",
    "hashtags",
  ] as const;
  for (const key of scalarKeys) {
    if (patch[key] !== undefined) result[key] = patch[key];
  }
  if (patch.sections !== undefined) {
    result.sections = Object.fromEntries(
      patch.sections.map((section) => [section.key, section.text]),
    );
  }
  if (patch.overlays !== undefined) {
    result.overlays = patch.overlays.map((overlay) => ({
      timestamp_seconds: overlay.at_seconds,
      text: overlay.text,
    }));
  }
  if (patch.cues !== undefined) {
    result.cues = patch.cues.map((cue) => ({
      timestamp_seconds: cue.at_seconds,
      duration_seconds: cue.duration_seconds,
      broll_id: cue.slot,
      label: cue.label,
    }));
  }
  return result;
};

const normalizeComplianceReport = (payload: unknown): ComplianceReport => {
  const record = valueRecord(unwrapObject<unknown>(payload));
  return {
    episode_id: valueString(record.episode_id),
    gates: normalizeCompliance(record.gates),
    all_passed: Boolean(record.all_passed),
    blocking: Array.isArray(record.blocking)
      ? record.blocking.map((item) => String(item))
      : [],
  };
};

export const api = {
  baseUrl: API_URL,

  health: async () => request<unknown>("/health", undefined, 2_500),

  overview: async () =>
    unwrapObject<OverviewData>(await request<unknown>("/overview")),

  stories: async () =>
    unwrapList<Story>(await request<unknown>("/stories"), ["stories"]),

  refreshResearch: async () =>
    unwrapList<Story>(
      await request<unknown>("/research/refresh", { method: "POST" }, 15_000),
      ["stories"],
    ),

  selectStory: async (id: string, selected: boolean) =>
    unwrapObject<Story>(
      await request<unknown>(`/stories/${encodeURIComponent(id)}/select`, {
        ...json({ selected }),
      }),
    ),

  episodes: async () =>
    unwrapList<unknown>(await request<unknown>("/episodes"), ["episodes"]).map(
      normalizeEpisode,
    ),

  episode: async (id: string) =>
    normalizeEpisode(await request<unknown>(`/episodes/${encodeURIComponent(id)}`)),

  createEpisode: async (payload: {
    kind: Episode["kind"];
    date?: string;
    angle: string;
    story_ids: string[];
  }) =>
    normalizeEpisode(
      await request<unknown>("/episodes", json(payload)),
    ),

  patchEpisode: async (id: string, payload: EditableEpisodePatch) =>
    normalizeEpisode(
      await request<unknown>(`/episodes/${encodeURIComponent(id)}`, {
        ...json(serializeEpisodePatch(payload), "PATCH"),
      }),
    ),

  draftEpisode: async (
    id: string,
    provider: "auto" | "offline" | "anthropic" = "auto",
  ) =>
    normalizeEpisode(
      await request<unknown>(`/episodes/${encodeURIComponent(id)}/draft`, {
        ...json({ provider }),
      }, 30_000),
    ),

  approveEpisode: async (id: string) =>
    normalizeEpisode(
      await request<unknown>(
        `/episodes/${encodeURIComponent(id)}/approve`,
        { method: "POST" },
      ),
    ),

  compliance: async (id: string) =>
    normalizeComplianceReport(
      await request<unknown>(`/episodes/${encodeURIComponent(id)}/compliance`),
    ),

  updateCompliance: async (
    episodeId: string,
    gateId: string,
    passed: boolean,
  ) =>
    normalizeComplianceReport(
      await request<unknown>(
        `/episodes/${encodeURIComponent(episodeId)}/compliance/${encodeURIComponent(gateId)}`,
        json({ passed }, "PUT"),
      ),
    ),

  voiceEpisode: async (id: string) =>
    unwrapObject<VoiceArtifact>(
      await request<unknown>(
        `/episodes/${encodeURIComponent(id)}/voice`,
        { method: "POST" },
        30_000,
      ),
    ),

  renderEpisode: async (id: string) =>
    unwrapObject<RenderJob>(
      await request<unknown>(
        `/episodes/${encodeURIComponent(id)}/render`,
        { method: "POST" },
        30_000,
      ),
    ),

  publishPackage: async (id: string) =>
    unwrapObject<PublishPackage>(
      await request<unknown>(
        `/episodes/${encodeURIComponent(id)}/publish-package`,
        { method: "POST" },
        30_000,
      ),
    ),

  renderJob: async (id: string) =>
    unwrapObject<RenderJob>(
      await request<unknown>(`/render-jobs/${encodeURIComponent(id)}`),
    ),

  renderJobs: async () =>
    unwrapList<RenderJob>(
      await request<unknown>("/render-jobs"),
      ["render_jobs", "jobs"],
    ),

  /* --- Post Studio ------------------------------------------------- */

  capabilities: async () =>
    unwrapObject<Capabilities>(
      await request<unknown>("/capabilities", undefined, 20_000),
    ),

  posts: async () =>
    unwrapList<Post>(await request<unknown>("/posts"), ["posts"]),

  post: async (id: string) =>
    unwrapObject<Post>(
      await request<unknown>(`/posts/${encodeURIComponent(id)}`),
    ),

  createPost: async (payload: {
    prompt: string;
    format: PostFormat;
    slides?: number;
    image_provider?: ImageProvider;
    direction_provider?: "auto" | "offline" | "anthropic";
    generate?: boolean;
  }) => unwrapObject<Post>(await request<unknown>("/posts", json(payload), 20_000)),

  patchPost: async (id: string, payload: PostPatchBody) =>
    unwrapObject<Post>(
      await request<unknown>(
        `/posts/${encodeURIComponent(id)}`,
        json(payload, "PATCH"),
      ),
    ),

  generatePost: async (
    id: string,
    payload: {
      image_provider?: ImageProvider;
      direction_provider?: "auto" | "offline" | "anthropic";
      slides?: number;
      redraft?: boolean;
    } = {},
  ) =>
    unwrapObject<Post>(
      await request<unknown>(
        `/posts/${encodeURIComponent(id)}/generate`,
        json(payload),
        20_000,
      ),
    ),

  uploadPostAsset: async (id: string, file: File, kind: "image" | "video") => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return unwrapObject<Post>(
      await request<unknown>(
        `/posts/${encodeURIComponent(id)}/upload`,
        { method: "POST", body: form },
        60_000,
      ),
    );
  },

  approvePost: async (id: string) =>
    unwrapObject<Post>(
      await request<unknown>(`/posts/${encodeURIComponent(id)}/approve`, {
        method: "POST",
      }),
    ),

  publishPreview: async (id: string) =>
    unwrapObject<PublishPreview>(
      await request<unknown>(
        `/posts/${encodeURIComponent(id)}/publish-preview`,
        undefined,
        20_000,
      ),
    ),

  publishPost: async (id: string, expectedRevision: number) =>
    unwrapObject<Post>(
      await request<unknown>(
        `/posts/${encodeURIComponent(id)}/publish`,
        json({ confirm: true, expected_revision: expectedRevision }),
        180_000,
      ),
    ),
};
