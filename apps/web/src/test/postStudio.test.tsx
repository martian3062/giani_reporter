import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import App from "../App";
import { DeskProvider } from "../DeskContext";
import type { Capabilities, Post, PublishPreview } from "../types";

const capabilities: Capabilities = {
  drafting: { anthropic: true, offline_fallback: true },
  voice: { elevenlabs: false },
  images: {
    resolved_provider: "gemini",
    configured: ["gemini", "imagen", "offline"],
    gemini: true,
    openai: false,
    stability: false,
    replicate: false,
  },
  media_host: { mode: "local", ready: true, detail: "https://desk.example.com" },
  instagram: {
    configured: true,
    publish_enabled: true,
    login_mode: "facebook",
    api_base: "https://graph.facebook.com/v21.0",
    account: { username: "giani.desk" },
    quota: { quota_usage: 1 },
    error: "",
  },
  post_formats: [
    {
      id: "feed_square",
      label: "Feed square 1:1",
      aspect: "1:1",
      width: 1080,
      height: 1080,
      max_assets: 1,
    },
    {
      id: "carousel",
      label: "Carousel 4:5",
      aspect: "4:5",
      width: 1080,
      height: 1350,
      max_assets: 10,
    },
  ],
  post_checks: [],
  daily_publish_limit: 5,
};

const allChecks = (passed: boolean) => ({
  prompt_present: passed,
  caption_length: passed,
  hashtag_count: passed,
  alt_text_present: passed,
  ai_disclosure: passed,
  advice_safe: passed,
  neutral_anchor: passed,
  asset_count: passed,
  assets_current: passed,
  no_demo_assets: passed,
  human_reviewed: false,
});

const basePost = (overrides: Partial<Post> = {}): Post => ({
  id: "post-1",
  prompt: "A quiet server room at dawn",
  format: "feed_square",
  status: "review",
  headline: "Server rooms at dawn",
  caption: "Server rooms at dawn.",
  hashtags: ["#AI", "#Infrastructure"],
  alt_text: "A dark server room.",
  ai_disclosure: "Visual generated with AI.",
  image_prompts: ["A quiet server room at dawn"],
  direction_provider: "anthropic",
  image_provider: "gemini",
  checks: allChecks(true),
  revision: 2,
  approved_revision: 0,
  error: "",
  created_at: "2026-08-03T00:00:00Z",
  updated_at: "2026-08-03T00:00:00Z",
  assets: [
    {
      id: "asset-1",
      post_id: "post-1",
      position: 0,
      kind: "image",
      provider: "gemini",
      prompt_used: "A quiet server room at dawn",
      mime: "image/jpeg",
      width: 1080,
      height: 1080,
      bytes: 220_000,
      sha256: "abc",
      preview_path: "/api/posts/post-1/assets/asset-1/file",
      is_demo: false,
      post_revision: 2,
      created_at: "2026-08-03T00:00:00Z",
    },
  ],
  publications: [],
  ...overrides,
});

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/**
 * The desk boots into demo mode unless /health, /stories, and /episodes all
 * answer, so every Post Studio test needs that handshake stubbed.
 */
const routeFetch = (handlers: Record<string, () => Response>) => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      for (const [pattern, handler] of Object.entries(handlers)) {
        const [patternMethod, patternPath] = pattern.split(" ");
        if (method === patternMethod && url.endsWith(patternPath)) {
          return handler();
        }
      }
      if (url.endsWith("/health")) return jsonResponse({ status: "ok" });
      if (url.endsWith("/stories")) {
        return jsonResponse([{ id: "story-1", selected: true }]);
      }
      if (url.endsWith("/episodes")) return jsonResponse([]);
      if (url.endsWith("/render-jobs")) return jsonResponse([]);
      return jsonResponse({ detail: `unmocked ${method} ${url}` }, 404);
    }),
  );
};

const renderPosts = () =>
  render(
    <MemoryRouter initialEntries={["/posts"]}>
      <DeskProvider>
        <App />
      </DeskProvider>
    </MemoryRouter>,
  );

describe("Post Studio", () => {
  it("refuses to run against the browser demo workspace", async () => {
    renderPosts();
    expect(
      await screen.findByText(/the api is not connected/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /generate post/i }),
    ).not.toBeInTheDocument();
  });

  it("shows generated slides and the failing checks that block approval", async () => {
    const post = basePost({
      checks: { ...allChecks(true), ai_disclosure: false },
    });
    routeFetch({
      "GET /capabilities": () => jsonResponse(capabilities),
      "GET /posts": () => jsonResponse([post]),
    });
    renderPosts();

    const slide = await screen.findByRole("img", {
      name: /a dark server room/i,
    });
    expect(slide).toHaveAttribute(
      "src",
      expect.stringContaining("/api/posts/post-1/assets/asset-1/file"),
    );

    const checks = screen.getByRole("list", { name: /publish checks/i });
    const disclosure = within(checks).getByText(/ai disclosure in caption/i);
    expect(disclosure.closest("li")).toHaveClass("fail");

    expect(
      screen.getByRole("button", { name: /approve revision 2/i }),
    ).toBeDisabled();
  });

  it("warns when slides are unpublishable placeholders", async () => {
    routeFetch({
      "GET /capabilities": () =>
        jsonResponse({
          ...capabilities,
          images: { ...capabilities.images, resolved_provider: "offline" },
        }),
      "GET /posts": () => jsonResponse([]),
    });
    renderPosts();

    expect(
      await screen.findByText(/no image model configured/i),
    ).toBeInTheDocument();
  });

  it("requires a typed confirmation before publishing", async () => {
    const user = userEvent.setup();
    const approved = basePost({
      status: "approved",
      approved_revision: 2,
      checks: { ...allChecks(true), human_reviewed: true },
    });
    const preview: PublishPreview = {
      post_id: "post-1",
      revision: 2,
      target: "instagram",
      format: "feed_square",
      caption: "Server rooms at dawn.\n\n#AI #Infrastructure",
      slides: 1,
      media_urls: ["https://desk.example.com/api/public/media/abc.jpg"],
      blockers: [],
      ready: true,
      quota: {},
      account: { username: "giani.desk" },
    };
    const publishCall = vi.fn(() =>
      jsonResponse({
        ...approved,
        status: "published",
        publications: [
          {
            id: "pub-1",
            post_id: "post-1",
            status: "published",
            post_revision: 2,
            container_id: "c1",
            media_id: "media-1",
            permalink: "https://instagr.am/p/media-1",
            ig_user_id: "1784",
            error: "",
            created_at: "2026-08-03T00:00:00Z",
            updated_at: "2026-08-03T00:00:00Z",
          },
        ],
      }),
    );
    routeFetch({
      "GET /capabilities": () => jsonResponse(capabilities),
      "GET /posts": () => jsonResponse([approved]),
      "GET /publish-preview": () => jsonResponse(preview),
      "POST /publish": publishCall,
    });
    renderPosts();

    await user.click(
      await screen.findByRole("button", { name: /check instagram/i }),
    );

    const publishButton = await screen.findByRole("button", {
      name: /publish to instagram/i,
    });
    expect(publishButton).toBeDisabled();
    expect(screen.getByText(/giani\.desk/)).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("PUBLISH"), "publish");
    expect(publishButton).toBeDisabled();

    await user.clear(screen.getByPlaceholderText("PUBLISH"));
    await user.type(screen.getByPlaceholderText("PUBLISH"), "PUBLISH");
    expect(publishButton).toBeEnabled();

    await user.click(publishButton);
    await waitFor(() => expect(publishCall).toHaveBeenCalledOnce());
    expect(
      await screen.findByRole("link", { name: /open on instagram/i }),
    ).toHaveAttribute("href", "https://instagr.am/p/media-1");
  });

  it("surfaces the backend's blockers instead of a bare status code", async () => {
    const user = userEvent.setup();
    const approved = basePost({
      status: "approved",
      approved_revision: 2,
      checks: { ...allChecks(true), human_reviewed: true },
    });
    routeFetch({
      "GET /capabilities": () => jsonResponse(capabilities),
      "GET /posts": () => jsonResponse([approved]),
      "GET /publish-preview": () =>
        jsonResponse(
          {
            detail: {
              message: "post is not publishable",
              blockers: ["Set INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN"],
            },
          },
          409,
        ),
    });
    renderPosts();

    await user.click(
      await screen.findByRole("button", { name: /check instagram/i }),
    );

    expect(
      await screen.findByText(/set instagram_user_id and instagram_access_token/i),
    ).toBeInTheDocument();
  });
});
