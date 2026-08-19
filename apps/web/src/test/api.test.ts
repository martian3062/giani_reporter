import { api, normalizeEpisode, serializeEpisodePatch } from "../api";

const rawBackendEpisode = {
  id: "episode-contract-fixture",
  kind: "daily",
  status: "draft",
  date: "2026-07-27",
  angle: "Reliability is becoming the real product advantage.",
  story_ids: ["story-1", "story-2", "story-3"],
  script: "A short fixture script.",
  sections: {
    hook: "The next race is operational.",
    story_1: "Story one.",
    story_2: "Story two.",
    story_3: "Story three.",
    take: "Three sources point toward reliable systems.",
    sign_off: "Keep your signal clean.",
  },
  title: "The Operational AI Race",
  description: "Sources:\nhttps://example.com/one",
  hashtags: ["#AI", "#Shorts"],
  overlays: [{ timestamp_seconds: 4, text: "RELIABILITY WINS" }],
  cues: [
    {
      timestamp_seconds: 0,
      duration_seconds: 5,
      broll_id: 1,
      label: "Cold open",
    },
  ],
  word_count: 157,
  runtime_seconds: 63,
  compliance: {
    opinion: true,
    format_varied: false,
    synthetic_disclosure: false,
  },
  updated_at: "2026-07-27T12:00:00Z",
};

describe("backend episode adapter", () => {
  it("normalizes map-shaped sections, compliance, overlays, and cues", () => {
    const episode = normalizeEpisode({ data: rawBackendEpisode });

    expect(episode.kind).toBe("daily");
    expect(episode.status).toBe("draft");
    expect(episode.sections.map((section) => section.key)).toEqual([
      "hook",
      "story_1",
      "story_2",
      "story_3",
      "take",
      "sign_off",
    ]);
    expect(episode.compliance).toContainEqual(
      expect.objectContaining({ id: "opinion", passed: true }),
    );
    expect(episode.cues[0]).toEqual(
      expect.objectContaining({ at_seconds: 0, slot: 1 }),
    );
    expect(episode.overlays[0]).toEqual(
      expect.objectContaining({ at_seconds: 4, text: "RELIABILITY WINS" }),
    );
  });

  it("serializes only editable fields back to backend maps", () => {
    const normalized = normalizeEpisode(rawBackendEpisode);
    const patch = serializeEpisodePatch({
      angle: normalized.angle,
      sections: normalized.sections,
      cues: normalized.cues,
      overlays: normalized.overlays,
    });

    expect(patch.sections).toEqual(rawBackendEpisode.sections);
    expect(patch.cues).toEqual(rawBackendEpisode.cues);
    expect(patch.overlays).toEqual(rawBackendEpisode.overlays);
    expect(patch).not.toHaveProperty("id");
    expect(patch).not.toHaveProperty("status");
    expect(patch).not.toHaveProperty("compliance");
    expect(patch).not.toHaveProperty("word_count");
  });

  it("drafts with provider only and never sends the angle in DraftRequest", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(rawBackendEpisode), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await api.draftEpisode(rawBackendEpisode.id);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ provider: "auto" });
    expect(String(init?.body)).not.toContain("angle");
  });
});
