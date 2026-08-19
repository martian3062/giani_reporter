import type {
  BrollCue,
  ComplianceGate,
  DemoSnapshot,
  Episode,
  Overlay,
  ScriptSection,
  Story,
} from "./types";

const hoursAgo = (hours: number) =>
  new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();

export const complianceTemplate: ComplianceGate[] = [
  {
    id: "opinion",
    label: "Episode contains a stated opinion or argument",
    passed: false,
  },
  {
    id: "take_connects_stories",
    label: "The take connects the selected stories",
    passed: false,
  },
  {
    id: "format_varied",
    label: "Format varies from the previous three editions",
    passed: false,
  },
  {
    id: "advice_safe",
    label: "No medical, legal, financial, or political advice",
    passed: false,
  },
  {
    id: "neutral_anchor",
    label: "Anchor uses neutral AI Desk framing",
    passed: false,
  },
  {
    id: "figures_sourced",
    label: "Every figure is traced to a source",
    passed: false,
  },
  {
    id: "no_verify_tags",
    label: "No [VERIFY] tags remain",
    passed: false,
  },
  {
    id: "sources_linked",
    label: "Every source is linked in the description",
    passed: false,
  },
  {
    id: "synthetic_disclosure",
    label: "Synthetic-content disclosure is queued",
    passed: false,
  },
  {
    id: "broll_cadence",
    label: "B-roll appears at least every 12 seconds",
    passed: false,
  },
  {
    id: "one_upload_today",
    label: "This is the only upload scheduled today",
    passed: false,
  },
];

export const demoStories: Story[] = [
  {
    id: "demo-01",
    title: "Open model team publishes a compact reasoning checkpoint",
    source: "Demo Wire",
    url: "https://example.com/demo/open-reasoning",
    published_at: hoursAgo(1.2),
    summary:
      "A fictional model release shows how a small checkpoint could trade breadth for faster tool use.",
    why_it_matters:
      "Smaller inference footprints could make useful agents viable on ordinary developer hardware.",
    score: 96,
    selected: true,
    topic: "Models",
    is_demo: true,
  },
  {
    id: "demo-02",
    title: "Cloud labs test a shared standard for agent handoffs",
    source: "Sample Ledger",
    url: "https://example.com/demo/agent-handoffs",
    published_at: hoursAgo(2.4),
    summary:
      "A fictional working group proposes a common envelope for agents to pass context and permissions.",
    why_it_matters:
      "Interoperable handoffs may matter more than another isolated benchmark win.",
    score: 92,
    selected: true,
    topic: "Agents",
    is_demo: true,
  },
  {
    id: "demo-03",
    title: "Chip startup previews lower-power inference accelerator",
    source: "Prototype Press",
    url: "https://example.com/demo/inference-chip",
    published_at: hoursAgo(3.1),
    summary:
      "A fictional accelerator design targets sustained inference instead of peak training throughput.",
    why_it_matters:
      "The cost of serving models is becoming a product constraint, not only an infrastructure concern.",
    score: 89,
    selected: true,
    topic: "Compute",
    is_demo: true,
  },
  {
    id: "demo-04",
    title: "Research benchmark shifts focus from answers to recovery",
    source: "Demo Review",
    url: "https://example.com/demo/recovery-benchmark",
    published_at: hoursAgo(4.5),
    summary:
      "A sample benchmark measures whether an agent can recognize and recover from a wrong first move.",
    why_it_matters:
      "Reliable recovery is a stronger production signal than polished one-shot demos.",
    score: 86,
    selected: false,
    topic: "Research",
    is_demo: true,
  },
  {
    id: "demo-05",
    title: "Design tools trial provenance labels inside generated assets",
    source: "Sample Ledger",
    url: "https://example.com/demo/provenance",
    published_at: hoursAgo(5.2),
    summary:
      "A fictional design suite embeds edit history and generation provenance in exported media.",
    why_it_matters:
      "Provenance that survives export could make disclosure less dependent on creator memory.",
    score: 81,
    selected: false,
    topic: "Policy",
    is_demo: true,
  },
  {
    id: "demo-06",
    title: "Voice platform adds local pronunciation dictionaries",
    source: "Prototype Press",
    url: "https://example.com/demo/voice-dictionary",
    published_at: hoursAgo(6.8),
    summary:
      "A fictional speech platform lets production teams version names and technical terms per show.",
    why_it_matters:
      "A repeatable pronunciation layer removes a common source of costly voice retakes.",
    score: 77,
    selected: false,
    topic: "Audio",
    is_demo: true,
  },
  {
    id: "demo-07",
    title: "Developer survey finds evaluation work moving earlier",
    source: "Demo Wire",
    url: "https://example.com/demo/evaluation",
    published_at: hoursAgo(8.3),
    summary:
      "A fictional survey says teams are designing evaluation cases before prompt and tool implementation.",
    why_it_matters:
      "Teams may be treating evals as product requirements instead of a launch-day audit.",
    score: 72,
    selected: false,
    topic: "Developer tools",
    is_demo: true,
  },
  {
    id: "demo-08",
    title: "Synthetic media workflow standardizes editorial sign-off",
    source: "Demo Review",
    url: "https://example.com/demo/sign-off",
    published_at: hoursAgo(11.5),
    summary:
      "A fictional newsroom workflow records a human approval at script, voice, and publish stages.",
    why_it_matters:
      "Visible judgment points make automation auditable without slowing the entire production line.",
    score: 68,
    selected: false,
    topic: "Media",
    is_demo: true,
  },
];

export const demoSections: ScriptSection[] = [
  {
    key: "hook",
    label: "Hook",
    target_words: 12,
    text: "The next AI race may be won far away from the biggest model.",
  },
  {
    key: "story-1",
    label: "Story 01",
    target_words: 60,
    text: "A compact reasoning checkpoint is putting speed ahead of spectacle. The sample release is designed for tool use on modest hardware. That matters because useful agents cannot live on benchmark charts alone. Developers need systems that answer quickly, run affordably, and stay close to the work.",
  },
  {
    key: "story-2",
    label: "Story 02",
    target_words: 50,
    text: "Cloud labs are also testing a common language for agent handoffs. The goal is simple. Move context and permissions without rebuilding every connection. If that works, the winning agent stack may look less like one super-app and more like a dependable newsroom.",
  },
  {
    key: "story-3",
    label: "Story 03",
    target_words: 45,
    text: "Meanwhile, a new accelerator concept targets the cost of serving models. It optimizes sustained inference instead of headline training speed. That shift puts power use and latency inside the product conversation, where users actually feel them.",
  },
  {
    key: "take",
    label: "The take",
    target_words: 40,
    text: "Here is the pattern ... AI is moving from impressive objects to working systems. Smaller models, cleaner handoffs, and cheaper inference all reward operational discipline. The next advantage will not be one giant leap. It will be fewer broken steps.",
  },
  {
    key: "sign-off",
    label: "Sign-off",
    target_words: 8,
    text: "This is Mira. Keep your signal clean.",
  },
];

export const demoCues: BrollCue[] = [
  { id: "cue-1", at_seconds: 0, duration_seconds: 4, slot: 1, label: "Cold open" },
  { id: "cue-2", at_seconds: 13, duration_seconds: 5, slot: 4, label: "Chip macro" },
  { id: "cue-3", at_seconds: 27, duration_seconds: 5, slot: 2, label: "Data flow" },
  { id: "cue-4", at_seconds: 41, duration_seconds: 5, slot: 7, label: "Neural net" },
  { id: "cue-5", at_seconds: 55, duration_seconds: 5, slot: 12, label: "Datacenter" },
  { id: "cue-6", at_seconds: 69, duration_seconds: 5, slot: 14, label: "Transition" },
  { id: "cue-7", at_seconds: 84, duration_seconds: 5, slot: 15, label: "Outro" },
];

export const demoOverlays: Overlay[] = [
  { id: "overlay-1", at_seconds: 1, text: "THE SMALLER MODEL RACE" },
  { id: "overlay-2", at_seconds: 17, text: "SPEED > SPECTACLE" },
  { id: "overlay-3", at_seconds: 43, text: "HANDOFFS BECOME INFRASTRUCTURE" },
  { id: "overlay-4", at_seconds: 70, text: "FEWER BROKEN STEPS" },
];

const scriptFromSections = (sections: ScriptSection[]) =>
  sections.map((section) => section.text).join("\n\n");

export const activeDemoEpisode: Episode = {
  id: "ep-demo-today",
  kind: "daily",
  status: "draft",
  date: new Date().toISOString().slice(0, 10),
  angle:
    "The competitive edge is shifting from model size to the reliability of the whole system.",
  story_ids: ["demo-01", "demo-02", "demo-03"],
  script: scriptFromSections(demoSections),
  sections: demoSections,
  title: "AI’s Next Edge Is Operational",
  description:
    "Three signals point away from model spectacle and toward dependable systems.\n\nSources are attached below before publication.\n\nEdited and approved by a human producer.",
  hashtags: ["#AI", "#AIAgents", "#DeveloperTools", "#Inference", "#Shorts"],
  overlays: demoOverlays,
  cues: demoCues,
  word_count: 209,
  runtime_seconds: 84,
  compliance: complianceTemplate,
  updated_at: new Date().toISOString(),
};

const archivedEpisode = (
  id: string,
  offset: number,
  title: string,
  status: Episode["status"],
): Episode => ({
  ...activeDemoEpisode,
  id,
  date: new Date(Date.now() - offset * 86_400_000).toISOString().slice(0, 10),
  title,
  status,
  compliance: complianceTemplate.map((gate) => ({ ...gate, passed: true })),
  updated_at: hoursAgo(offset * 24),
});

export const demoSnapshot: DemoSnapshot = {
  stories: demoStories,
  episodes: [
    activeDemoEpisode,
    archivedEpisode("ep-demo-01", 1, "Agents Learn to Recover", "packaged"),
    archivedEpisode("ep-demo-02", 2, "The New Inference Constraint", "packaged"),
    archivedEpisode("ep-demo-03", 3, "Provenance Moves Into the File", "approved"),
    archivedEpisode("ep-demo-04", 4, "Why Evals Moved Left", "packaged"),
  ],
  jobs: [
    {
      id: "render-demo-active",
      episode_id: "ep-demo-today",
      status: "running",
      progress: 64,
      stage: "Compositing captions + overlays",
      output_path: null,
      error: null,
    },
    {
      id: "render-demo-01",
      episode_id: "ep-demo-01",
      status: "complete",
      progress: 100,
      stage: "Delivery package ready",
      output_path: "/renders/ep-demo-01/final.mp4",
      error: null,
    },
    {
      id: "render-demo-03",
      episode_id: "ep-demo-03",
      status: "complete",
      progress: 100,
      stage: "Quality control passed",
      output_path: "/renders/ep-demo-03/final.mp4",
      error: null,
    },
  ],
  voices: {
    "ep-demo-today": {
      episode_id: "ep-demo-today",
      provider: "demo",
      output_path: "/voice/ep-demo-today.demo.txt",
      is_demo: true,
      error: "",
    },
    "ep-demo-01": {
      episode_id: "ep-demo-01",
      provider: "demo",
      output_path: "/voice/ep-demo-01.demo.txt",
      is_demo: true,
      error: "",
    },
  },
};

export const brollSlots = [
  "Cold open",
  "Data flow",
  "Code scroll",
  "Chip macro",
  "City tech",
  "Robot arm",
  "Neural net",
  "Tech office",
  "Phone close-up",
  "Chart rising",
  "Chart falling",
  "Datacenter exterior",
  "Research lab",
  "Light transition",
  "Outro",
];
