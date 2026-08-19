import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Image as ImageIcon,
  Instagram,
  Loader2,
  RefreshCw,
  Send,
  Sparkles,
  Upload,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api";
import { useDesk } from "../DeskContext";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";
import type {
  Capabilities,
  ImageProvider,
  Post,
  PostFormat,
  PublishPreview,
} from "../types";

const FORMAT_FALLBACK: { id: PostFormat; label: string; max_assets: number }[] = [
  { id: "feed_square", label: "Feed square 1:1", max_assets: 1 },
  { id: "feed_portrait", label: "Feed portrait 4:5", max_assets: 1 },
  { id: "feed_landscape", label: "Feed landscape 1.91:1", max_assets: 1 },
  { id: "carousel", label: "Carousel 4:5", max_assets: 10 },
  { id: "story", label: "Story 9:16", max_assets: 1 },
  { id: "reel", label: "Reel 9:16", max_assets: 1 },
];

const PROVIDERS: { id: ImageProvider; label: string }[] = [
  { id: "auto", label: "Auto (best configured)" },
  { id: "gemini", label: "Gemini image" },
  { id: "imagen", label: "Imagen" },
  { id: "openai", label: "OpenAI images" },
  { id: "stability", label: "Stability" },
  { id: "replicate", label: "Replicate" },
  { id: "offline", label: "Offline placeholder" },
];

const CHECK_LABELS: Record<string, string> = {
  prompt_present: "Human prompt on record",
  caption_length: "Caption within 2,200 characters",
  hashtag_count: "Hashtags well formed",
  alt_text_present: "Alt text written",
  ai_disclosure: "AI disclosure in caption",
  advice_safe: "No advice language",
  neutral_anchor: "No credential framing",
  asset_count: "Slide count matches format",
  assets_current: "Slides match this revision",
  no_demo_assets: "No demo placeholder attached",
  human_reviewed: "Human approved this revision",
};

const mediaUrl = (path: string) =>
  path.startsWith("/api/")
    ? `${api.baseUrl.replace(/\/api$/, "")}${path}`
    : path;

const errorText = (error: unknown) => {
  if (error instanceof ApiError) {
    return error.blockers.length
      ? `${error.message}: ${error.blockers.join("; ")}`
      : error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
};

export function PostStudioPage() {
  const { mode, notify } = useDesk();
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [prompt, setPrompt] = useState("");
  const [format, setFormat] = useState<PostFormat>("feed_square");
  const [slides, setSlides] = useState(3);
  const [provider, setProvider] = useState<ImageProvider>("auto");
  const [busy, setBusy] = useState<string>("");
  const [preview, setPreview] = useState<PublishPreview | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const uploadRef = useRef<HTMLInputElement>(null);

  const active = useMemo(
    () => posts.find((post) => post.id === activeId),
    [activeId, posts],
  );
  const formats = capabilities?.post_formats ?? FORMAT_FALLBACK;
  const activeFormat = formats.find((item) => item.id === format);
  const supportsSlides = (activeFormat?.max_assets ?? 1) > 1;

  const replacePost = useCallback((next: Post) => {
    setPosts((current) => {
      const exists = current.some((post) => post.id === next.id);
      return exists
        ? current.map((post) => (post.id === next.id ? next : post))
        : [next, ...current];
    });
    setActiveId(next.id);
  }, []);

  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;
    void Promise.allSettled([api.capabilities(), api.posts()]).then(
      ([capabilityResult, postsResult]) => {
        if (cancelled) return;
        if (capabilityResult.status === "fulfilled") {
          setCapabilities(capabilityResult.value);
        }
        if (postsResult.status === "fulfilled") {
          setPosts(postsResult.value);
          setActiveId((current) => current ?? postsResult.value[0]?.id);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [mode]);

  // Generation runs in the background on the API, so the desk polls until the
  // post leaves the generating state.
  useEffect(() => {
    if (mode !== "live" || active?.status !== "generating") return;
    const interval = window.setInterval(() => {
      void api
        .post(active.id)
        .then((fresh) => {
          replacePost(fresh);
          if (fresh.status === "review") {
            notify("Slides are ready for review.", "success");
          } else if (fresh.status === "planning" && fresh.error) {
            notify(fresh.error, "error");
          }
        })
        .catch(() => {
          // A single missed poll is not worth interrupting the operator.
        });
    }, 2_500);
    return () => window.clearInterval(interval);
  }, [active?.id, active?.status, mode, notify, replacePost]);

  useEffect(() => {
    setPreview(null);
    setConfirmText("");
  }, [activeId, active?.revision]);

  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    try {
      await action();
    } catch (error) {
      notify(errorText(error), "error");
    } finally {
      setBusy("");
    }
  };

  const handleGenerate = () =>
    run("generate", async () => {
      if (!prompt.trim()) {
        notify("Write the prompt first.", "error");
        return;
      }
      const created = await api.createPost({
        prompt: prompt.trim(),
        format,
        slides: supportsSlides ? slides : undefined,
        image_provider: provider,
        generate: format !== "reel",
      });
      replacePost(created);
      notify(
        format === "reel"
          ? "Reel created. Upload the rendered video below."
          : "Pipeline started. Slides are generating.",
        "success",
      );
    });

  const handleRegenerate = () =>
    run("regenerate", async () => {
      if (!active) return;
      replacePost(await api.generatePost(active.id, { redraft: false }));
      notify("Regenerating the slides with the same direction.", "info");
    });

  const handleRedraft = () =>
    run("redraft", async () => {
      if (!active) return;
      replacePost(await api.generatePost(active.id, { redraft: true }));
      notify("Rewriting the direction and the slides.", "info");
    });

  const handleSave = (patch: Parameters<typeof api.patchPost>[1]) =>
    run("save", async () => {
      if (!active) return;
      replacePost(await api.patchPost(active.id, patch));
      notify("Saved. Approval was reset for the new revision.", "success");
    });

  const handleUpload = (file: File) =>
    run("upload", async () => {
      if (!active) return;
      const kind = file.type.startsWith("video/") ? "video" : "image";
      replacePost(await api.uploadPostAsset(active.id, file, kind));
      notify(`${file.name} attached and normalized.`, "success");
    });

  const handleApprove = () =>
    run("approve", async () => {
      if (!active) return;
      replacePost(await api.approvePost(active.id));
      notify("Approved. This exact revision is now publishable.", "success");
    });

  const handlePreview = () =>
    run("preview", async () => {
      if (!active) return;
      const result = await api.publishPreview(active.id);
      setPreview(result);
      notify(
        result.ready
          ? "Ready to publish. Type PUBLISH to confirm."
          : `${result.blockers.length} blocker(s) remain.`,
        result.ready ? "success" : "error",
      );
    });

  const handlePublish = () =>
    run("publish", async () => {
      if (!active) return;
      const published = await api.publishPost(active.id, active.revision);
      replacePost(published);
      setConfirmText("");
      setPreview(null);
      notify("Published to Instagram.", "success");
    });

  if (mode !== "live") {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Post Studio"
          title="Prompt in, Instagram post out."
          description="One prompt becomes a caption, hashtags, alt text, and slides. You review every pixel before anything goes live."
        />
        <div className="empty-state">
          <Instagram size={31} />
          <h2>The API is not connected</h2>
          <p>
            This pipeline generates real media and publishes to a real account,
            so it never runs against the browser demo workspace. Start the
            FastAPI service and reload.
          </p>
        </div>
      </div>
    );
  }

  const checks = active?.checks ?? {};
  const failing = Object.entries(checks).filter(([, passed]) => !passed);
  const live = active?.publications.find((item) => item.status === "published");

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Post Studio"
        title="Prompt in, Instagram post out."
        description="One prompt becomes a caption, hashtags, alt text, and slides. You review every pixel before anything goes live."
        action={
          capabilities ? (
            <span className="provider-pill">
              <Sparkles size={15} />
              {capabilities.images.resolved_provider}
            </span>
          ) : null
        }
      />

      {capabilities?.images.resolved_provider === "offline" ? (
        <p className="demo-note">
          <strong>No image model configured.</strong> Slides will be visibly
          stamped placeholders and can never be published. Set{" "}
          <code>GOOGLE_API_KEY</code>, <code>OPENAI_API_KEY</code>,{" "}
          <code>STABILITY_API_KEY</code>, or <code>REPLICATE_API_TOKEN</code> in
          the API environment.
        </p>
      ) : null}

      <section className="post-brief" aria-label="New post">
        <label className="field">
          <span>Prompt</span>
          <textarea
            rows={3}
            value={prompt}
            placeholder="A quiet server room at dawn, blue light on the racks, shot on 35mm"
            onChange={(event) => setPrompt(event.target.value)}
          />
        </label>

        <div className="post-brief-controls">
          <label className="field">
            <span>Format</span>
            <select
              value={format}
              onChange={(event) => setFormat(event.target.value as PostFormat)}
            >
              {formats.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          {supportsSlides ? (
            <label className="field">
              <span>Slides</span>
              <input
                type="number"
                min={2}
                max={activeFormat?.max_assets ?? 10}
                value={slides}
                onChange={(event) => setSlides(Number(event.target.value))}
              />
            </label>
          ) : null}

          <label className="field">
            <span>Image model</span>
            <select
              value={provider}
              onChange={(event) =>
                setProvider(event.target.value as ImageProvider)
              }
            >
              {PROVIDERS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            className="button button-primary"
            onClick={() => void handleGenerate()}
            disabled={busy === "generate"}
          >
            {busy === "generate" ? (
              <Loader2 size={17} className="spin" />
            ) : (
              <Sparkles size={17} />
            )}
            Generate post
          </button>
        </div>
      </section>

      {posts.length ? (
        <nav className="post-switcher" aria-label="Recent posts">
          {posts.slice(0, 8).map((post) => (
            <button
              key={post.id}
              type="button"
              className={post.id === activeId ? "post-tab active" : "post-tab"}
              onClick={() => setActiveId(post.id)}
            >
              <StatusChip status={post.status} />
              <span>{post.headline || post.prompt.slice(0, 40)}</span>
            </button>
          ))}
        </nav>
      ) : null}

      {active ? (
        <section className="post-workbench">
          <div className="post-slides" aria-label="Generated slides">
            {active.status === "generating" ? (
              <div className="post-slide-skeleton">
                <Loader2 size={26} className="spin" />
                <p>Generating {active.image_prompts.length || ""} slide(s)…</p>
              </div>
            ) : null}

            {active.assets.map((asset) => (
              <figure
                key={asset.id}
                className={asset.is_demo ? "post-slide demo" : "post-slide"}
              >
                {asset.kind === "video" ? (
                  <video src={mediaUrl(asset.preview_path)} controls muted />
                ) : (
                  <img
                    src={mediaUrl(asset.preview_path)}
                    alt={active.alt_text || `Slide ${asset.position + 1}`}
                  />
                )}
                <figcaption>
                  <strong>
                    Slide {asset.position + 1} / {asset.provider}
                  </strong>
                  <span>
                    {asset.width}×{asset.height}
                    {asset.is_demo ? " / DEMO, not publishable" : ""}
                  </span>
                </figcaption>
              </figure>
            ))}

            {!active.assets.length && active.status !== "generating" ? (
              <div className="post-slide-skeleton">
                <ImageIcon size={26} />
                <p>{active.error || "No slides yet."}</p>
              </div>
            ) : null}
          </div>

          <div className="post-editor">
            <div className="post-editor-actions">
              <button
                type="button"
                className="button button-secondary button-compact"
                onClick={() => void handleRegenerate()}
                disabled={Boolean(busy) || active.status === "published"}
              >
                <RefreshCw size={15} className={busy === "regenerate" ? "spin" : ""} />
                New slides
              </button>
              <button
                type="button"
                className="button button-secondary button-compact"
                onClick={() => void handleRedraft()}
                disabled={Boolean(busy) || active.status === "published"}
              >
                <Sparkles size={15} />
                Rewrite everything
              </button>
              <button
                type="button"
                className="button button-secondary button-compact"
                onClick={() => uploadRef.current?.click()}
                disabled={Boolean(busy) || active.status === "published"}
              >
                <Upload size={15} />
                Use my own file
              </button>
              <input
                ref={uploadRef}
                type="file"
                accept="image/*,video/mp4"
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file) void handleUpload(file);
                }}
              />
            </div>

            <label className="field">
              <span>Headline</span>
              <input
                defaultValue={active.headline}
                key={`headline-${active.id}-${active.revision}`}
                onBlur={(event) => {
                  if (event.target.value !== active.headline) {
                    void handleSave({ headline: event.target.value });
                  }
                }}
              />
            </label>

            <label className="field">
              <span>
                Caption <small>{active.caption.length} / 2200</small>
              </span>
              <textarea
                rows={8}
                key={`caption-${active.id}-${active.revision}`}
                defaultValue={active.caption}
                onBlur={(event) => {
                  if (event.target.value !== active.caption) {
                    void handleSave({ caption: event.target.value });
                  }
                }}
              />
            </label>

            <label className="field">
              <span>Hashtags</span>
              <input
                key={`tags-${active.id}-${active.revision}`}
                defaultValue={active.hashtags.join(" ")}
                onBlur={(event) => {
                  const next = event.target.value.split(/\s+/).filter(Boolean);
                  if (next.join(" ") !== active.hashtags.join(" ")) {
                    void handleSave({ hashtags: next });
                  }
                }}
              />
            </label>

            <label className="field">
              <span>Alt text</span>
              <textarea
                rows={2}
                key={`alt-${active.id}-${active.revision}`}
                defaultValue={active.alt_text}
                onBlur={(event) => {
                  if (event.target.value !== active.alt_text) {
                    void handleSave({ alt_text: event.target.value });
                  }
                }}
              />
            </label>

            <ul className="post-checks" aria-label="Publish checks">
              {Object.entries(checks).map(([id, passed]) => (
                <li key={id} className={passed ? "pass" : "fail"}>
                  {passed ? (
                    <CheckCircle2 size={15} />
                  ) : (
                    <XCircle size={15} />
                  )}
                  <span>{CHECK_LABELS[id] ?? id}</span>
                </li>
              ))}
            </ul>

            <div className="post-publish">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => void handleApprove()}
                disabled={
                  Boolean(busy) ||
                  failing.filter(([id]) => id !== "human_reviewed").length > 0 ||
                  active.status === "published"
                }
              >
                <CheckCircle2 size={17} />
                Approve revision {active.revision}
              </button>

              <button
                type="button"
                className="button button-secondary"
                onClick={() => void handlePreview()}
                disabled={Boolean(busy) || active.status !== "approved"}
              >
                {busy === "preview" ? (
                  <Loader2 size={17} className="spin" />
                ) : (
                  <Instagram size={17} />
                )}
                Check Instagram
              </button>
            </div>

            {preview ? (
              <div
                className={preview.ready ? "publish-panel ready" : "publish-panel"}
              >
                <h3>
                  {preview.ready
                    ? "Ready to publish"
                    : "Not publishable yet"}
                </h3>
                {preview.blockers.length ? (
                  <ul className="publish-blockers">
                    {preview.blockers.map((blocker) => (
                      <li key={blocker}>
                        <AlertTriangle size={14} />
                        {blocker}
                      </li>
                    ))}
                  </ul>
                ) : null}

                {preview.ready ? (
                  <>
                    <p className="publish-warning">
                      This posts to{" "}
                      <strong>
                        {String(preview.account.username ?? "your account")}
                      </strong>{" "}
                      immediately and cannot be undone from this desk.
                    </p>
                    <label className="field">
                      <span>Type PUBLISH to confirm</span>
                      <input
                        value={confirmText}
                        onChange={(event) => setConfirmText(event.target.value)}
                        placeholder="PUBLISH"
                      />
                    </label>
                    <button
                      type="button"
                      className="button button-primary"
                      onClick={() => void handlePublish()}
                      disabled={confirmText !== "PUBLISH" || Boolean(busy)}
                    >
                      {busy === "publish" ? (
                        <Loader2 size={17} className="spin" />
                      ) : (
                        <Send size={17} />
                      )}
                      Publish to Instagram
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}

            {live ? (
              <p className="publish-result">
                <CheckCircle2 size={16} />
                Live as {live.media_id}.{" "}
                {live.permalink ? (
                  <a
                    className="text-link"
                    href={live.permalink}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open on Instagram <ExternalLink size={13} />
                  </a>
                ) : null}
              </p>
            ) : null}

            {active.error ? (
              <div className="run-error" role="alert">
                <AlertTriangle size={17} />
                <span>{active.error}</span>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
