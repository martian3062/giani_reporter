export type EpisodeStatus =
  | "planning"
  | "draft"
  | "approved"
  | "packaged";

export type RenderStatus = "queued" | "running" | "complete" | "failed";

export interface Story {
  id: string;
  title: string;
  source: string;
  url: string;
  published_at: string;
  summary: string;
  why_it_matters: string;
  score: number;
  selected: boolean;
  topic: string;
  is_demo: boolean;
}

export interface ScriptSection {
  key: string;
  label: string;
  text: string;
  target_words?: number;
}

export interface BrollCue {
  id: string;
  at_seconds: number;
  duration_seconds: number;
  slot: number;
  label: string;
}

export interface Overlay {
  id: string;
  at_seconds: number;
  text: string;
}

export interface ComplianceGate {
  id: string;
  label: string;
  passed: boolean;
  note?: string;
}

export interface Episode {
  id: string;
  kind: "daily" | "deep_dive";
  status: EpisodeStatus;
  date: string;
  angle: string;
  story_ids: string[];
  script: string;
  sections: ScriptSection[];
  title: string;
  description: string;
  hashtags: string[];
  overlays: Overlay[];
  cues: BrollCue[];
  word_count: number;
  runtime_seconds: number;
  compliance: ComplianceGate[];
  updated_at: string;
}

export interface RenderJob {
  id: string;
  episode_id: string;
  status: RenderStatus;
  progress: number;
  stage: string;
  output_path?: string | null;
  error?: string | null;
}

export interface VoiceArtifact {
  episode_id: string;
  provider: "demo" | "elevenlabs";
  output_path: string;
  is_demo: boolean;
  error: string;
}

export interface PublishPackage {
  episode_id: string;
  output_path: string;
  is_demo: boolean;
  warning: string;
}

export interface ComplianceReport {
  episode_id: string;
  gates: ComplianceGate[];
  all_passed: boolean;
  blocking: string[];
}

export interface EditableEpisodePatch {
  date?: string;
  angle?: string;
  story_ids?: string[];
  script?: string;
  sections?: ScriptSection[];
  title?: string;
  description?: string;
  hashtags?: string[];
  overlays?: Overlay[];
  cues?: BrollCue[];
}

export interface OverviewData {
  stories_reviewed: number;
  selected_count: number;
  minutes_to_air: number;
  completed_today: number;
  selected_stories: Story[];
  recent_episodes: Episode[];
}

export interface DemoSnapshot {
  stories: Story[];
  episodes: Episode[];
  jobs: RenderJob[];
  voices: Record<string, VoiceArtifact>;
}

export interface ToastMessage {
  id: number;
  message: string;
  tone: "success" | "error" | "info";
}

/* ------------------------------------------------------------------ */
/* Post Studio                                                         */
/* ------------------------------------------------------------------ */

export type PostFormat =
  | "feed_square"
  | "feed_portrait"
  | "feed_landscape"
  | "carousel"
  | "story"
  | "reel";

export type PostStatus =
  | "planning"
  | "generating"
  | "review"
  | "approved"
  | "publishing"
  | "published";

export type ImageProvider =
  | "auto"
  | "gemini"
  | "imagen"
  | "openai"
  | "stability"
  | "replicate"
  | "offline";

export interface PostAsset {
  id: string;
  post_id: string;
  position: number;
  kind: "image" | "video";
  provider: string;
  prompt_used: string;
  mime: string;
  width: number;
  height: number;
  bytes: number;
  sha256: string;
  preview_path: string;
  is_demo: boolean;
  post_revision: number;
  created_at: string;
}

export interface Publication {
  id: string;
  post_id: string;
  status: "pending" | "creating" | "publishing" | "published" | "failed";
  post_revision: number;
  container_id: string;
  media_id: string;
  permalink: string;
  ig_user_id: string;
  error: string;
  created_at: string;
  updated_at: string;
}

export interface Post {
  id: string;
  prompt: string;
  format: PostFormat;
  status: PostStatus;
  headline: string;
  caption: string;
  hashtags: string[];
  alt_text: string;
  ai_disclosure: string;
  image_prompts: string[];
  direction_provider: string;
  image_provider: string;
  checks: Record<string, boolean>;
  revision: number;
  approved_revision: number;
  error: string;
  created_at: string;
  updated_at: string;
  assets: PostAsset[];
  publications: Publication[];
}

export interface PostPatchBody {
  prompt?: string;
  headline?: string;
  caption?: string;
  hashtags?: string[];
  alt_text?: string;
  image_prompts?: string[];
}

export interface PublishPreview {
  post_id: string;
  revision: number;
  target: string;
  format: PostFormat;
  caption: string;
  slides: number;
  media_urls: string[];
  blockers: string[];
  ready: boolean;
  quota: Record<string, unknown>;
  account: Record<string, unknown>;
}

export interface PostFormatSpec {
  id: PostFormat;
  label: string;
  aspect: string;
  width: number;
  height: number;
  max_assets: number;
}

export interface Capabilities {
  drafting: { anthropic: boolean; offline_fallback: boolean };
  voice: { elevenlabs: boolean };
  images: {
    resolved_provider: string;
    configured: string[];
    gemini: boolean;
    openai: boolean;
    stability: boolean;
    replicate: boolean;
  };
  media_host: { mode: string; ready: boolean; detail: string };
  instagram: {
    configured: boolean;
    publish_enabled: boolean;
    login_mode: string;
    api_base: string;
    account: Record<string, unknown> | null;
    quota: Record<string, unknown> | null;
    error: string;
  };
  post_formats: PostFormatSpec[];
  post_checks: { id: string; label: string }[];
  daily_publish_limit: number;
}
