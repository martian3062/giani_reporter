# AI News Anchor — Build Plan

**Project:** Daily AI news, delivered by a consistent AI anchor
**Phase A:** Daily Broadcast (build now)
**Phase B:** Live Interactive Anchor (roadmap)
**Editorial model:** Human-in-the-loop — you supply the daily news + angle, the pipeline renders it

---

## 0. Stack at a Glance

| Layer | Tool | Status | Cost |
|---|---|---|---|
| News ingest | RSS bundle + Hacker News API | Build | $0 |
| Editorial / script | Claude + Master Prompt (§4) | Have | $0 |
| Voice | ElevenLabs Pro | **Owned** | $0 extra |
| Anchor face | HeyGen Creator (Avatar III) | Buy | $29/mo |
| B-roll / cold open | Veo 3.1 via Google AI Pro | **Owned** | $0 extra |
| Hero episodes | Hedra Character-3 (free tier) | Optional | $0 → $15 |
| Assembly | CapCut Desktop | Free | $0 |
| Orchestration | n8n (already running) | Have | $0 |

**Net new spend: $29/month.**

---

## 1. Format Decision

Two formats, one anchor. Do not deviate.

| | **Daily Bulletin** | **Weekly Deep Dive** |
|---|---|---|
| Length | 60–90 sec | 5–8 min |
| Aspect | 9:16 vertical | 16:9 horizontal |
| Word count | 150–225 words | 750–1,200 words |
| Platforms | Shorts, Reels, TikTok | YouTube long-form |
| Purpose | Subscriber growth | Watch-time + monetization |
| Cadence | Mon–Fri | Saturday |
| Stories | 3 | 1 (deep) |

**Why both:** Shorts grow the channel, long-form pays. Shorts alone caps your RPM near zero. Long-form alone grows too slowly to matter.

**Hard rule: one upload per day, maximum.** Volume is the exact signal YouTube's Generic/Repetitive Content policy is tuned to catch.

---

## 2. Phase 0 — One-Time Setup (Weekend 1)

Do this once. Everything after is repeatable.

### 2.1 Anchor identity — lock these forever

| Element | Decision | Why it's locked |
|---|---|---|
| Name | Pick one, 2 syllables, easy to say | Becomes the brand |
| Face | 1 generated portrait, front-facing, neutral | Face consistency = channel recognition |
| Voice | 1 ElevenLabs voice, saved settings | Voice change = viewers think channel was sold |
| Set | 1 background, reused every episode | Cheap familiarity |
| Sign-off | 1 catchphrase | Free brand recall |

> **Do not put "Dr.", "Analyst", "Expert", or any credential in the anchor's name, lower-third, or bio.** YouTube's July 2026 policy update explicitly targets AI personas that imply credentials on sensitive topics. Use a plain name and a neutral title like "AI Desk".

### 2.2 Generate the anchor face

Use Nano Banana Pro / Flux / Veo's image step. Prompt template:

```
Professional studio portrait of a [age 28-35] [gender] news presenter,
neutral friendly expression, direct eye contact with camera,
soft key light from front-left, subtle rim light,
solid dark blue-grey studio background, shallow depth of field,
smart casual blazer, shoulders visible, centered composition,
photorealistic, 85mm lens, 4K
```

**Requirements for HeyGen to animate it cleanly:**
- Front-facing, both eyes visible, no extreme angle
- Mouth closed or slightly open, neutral
- Head + shoulders in frame, head not cropped
- No hands near the face, no glasses glare, no busy background
- Export at 1080×1920 (vertical) — generate a 16:9 variant too

Generate 8–10 candidates. Pick one. **Save the exact prompt + seed** so you can regenerate variants later.

### 2.3 ElevenLabs voice — settings that work for news

Create → Voice Design or pick from library. Save as `[AnchorName]-Broadcast`.

| Setting | Value | Reason |
|---|---|---|
| Model (final) | Multilingual v2 | Highest quality for publish |
| Model (drafts) | Flash | Half the credit cost for test takes |
| Stability | 50–60 | Consistent but not robotic |
| Similarity | 80 | Locks the timbre |
| Style exaggeration | 0–20 | High style = theatrical = kills news credibility |
| Speaker boost | On | Cleaner presence |
| Format | MP3 192kbps | Available on Pro |

**Delivery tip:** ElevenLabs reads punctuation. Write scripts with short sentences and deliberate commas. Use `...` for a beat. Never use ALL CAPS (it distorts prosody) — use *emphasis* sparingly.

### 2.4 HeyGen avatar — click path

1. heygen.com → sign in → **Avatars** → **Create Avatar**
2. **Photo Avatar** → **Upload** your generated portrait
3. Name it `[AnchorName]-Vertical`
4. Wait for processing (~2–5 min)
5. Repeat with the 16:9 portrait → `[AnchorName]-Horizontal`
6. **Settings → Video** → default output **1080p**
7. Test render: **Create Video** → select avatar → **Audio** tab → **Upload Audio** → drop an ElevenLabs MP3 → Generate

> **Always use the Upload Audio path, never HeyGen's built-in TTS.** You already pay for ElevenLabs; using HeyGen's voice pays twice and breaks voice consistency.

### 2.5 B-roll library — build once, reuse forever

Generate **15 clips in Veo**, 8 sec each. At Veo 3.1 Lite (10 credits) that's 150 of your 1,000 monthly Flow credits. These get reused every episode for months.

| # | Clip | Prompt |
|---|---|---|
| 1 | Cold open | `Slow push-in through a dark server room, blue LED racks, volumetric haze, cinematic` |
| 2 | Data flow | `Abstract streams of light data flowing left to right, dark background, macro, slow` |
| 3 | Code scroll | `Over-shoulder shot of code scrolling on a monitor, shallow depth of field, dark room` |
| 4 | Chip macro | `Extreme macro of a computer chip, slow rotation, cool lighting, dust particles` |
| 5 | City tech | `Aerial drone shot over a city skyline at dusk, lights turning on, slow pan` |
| 6 | Robot arm | `Industrial robotic arm moving precisely in a clean white lab, side angle` |
| 7 | Neural net | `Abstract 3D neural network nodes pulsing and connecting, dark navy background` |
| 8 | Office | `Modern open-plan tech office, people out of focus walking past, slow dolly` |
| 9 | Phone | `Close-up of hands using a smartphone, screen glow on face, dark room` |
| 10 | Chart up | `Abstract 3D bar chart rising, glowing edges, dark background, slow camera orbit` |
| 11 | Chart down | `Abstract 3D line graph declining sharply, red glow, dark background` |
| 12 | Datacenter ext | `Exterior of a large datacenter building at dawn, cooling vapor, wide shot` |
| 13 | Lab | `Scientists at workstations in a research lab, blue monitor glow, slow pan` |
| 14 | Transition | `Abstract light sweep transition, blue to white, fast, motion blur` |
| 15 | Outro | `Slow pull-back from a glowing screen into darkness, cinematic, fade` |

Store in `/assets/broll/` named by number. **Do not regenerate these daily** — that's how people burn 1,000 Flow credits in a week for zero gain.

### 2.6 Brand kit

| Asset | Spec |
|---|---|
| Colours | 1 accent + dark neutral base. Pick and lock. |
| Lower third | Name + "AI Desk" + date. Template in CapCut. |
| Intro sting | 2 sec max. Logo + one sound hit. |
| Music bed | Royalty-free, −24 dB under voice. YouTube Audio Library. |
| Captions | Burned-in, bold sans, high contrast, bottom third |
| End card | "Full breakdown Saturday" + subscribe |

---

## 3. The Daily Production SOP

Target: **55–60 minutes/day**, start to publish.

| # | Step | Time | Tool |
|---|---|---|---|
| 1 | Review overnight story shortlist | 10 min | n8n digest (§6) or manual RSS |
| 2 | Pick 3 stories + decide **your angle** | 5 min | You — this is the non-delegable part |
| 3 | Run Master Prompt → get script | 3 min | Claude (§4) |
| 4 | Edit script by hand | 7 min | You |
| 5 | Render voice | 3 min | ElevenLabs |
| 6 | Render anchor video | 5–8 min | HeyGen (queue) |
| 7 | Assemble: anchor + B-roll + captions | 15 min | CapCut |
| 8 | Compliance check (§7) | 2 min | Checklist |
| 9 | Publish + metadata + disclosure toggle | 10 min | YouTube Studio, IG, TikTok |

### Assembly recipe (CapCut)

```
[0:00-0:03]  B-roll clip + hook text overlay        ← hook plays over B-roll
[0:03-0:30]  Anchor full-frame (Story 1)
             └ cut to B-roll at 0:12-0:17 (voice continues)
[0:30-0:50]  Anchor (Story 2)
             └ cut to B-roll at 0:38-0:43
[0:50-1:10]  Anchor (Story 3)
             └ cut to B-roll at 0:58-1:03
[1:10-1:25]  Anchor full-frame — THE TAKE (never cut away here)
[1:25-1:30]  End card
```

**Cut to B-roll every 8–12 seconds.** A static talking head for 90 straight seconds reads as low-effort to both viewers and reviewers.

---

## 4. The Master Prompt

This is the core asset. Paste your raw news in, get a broadcast-ready script out.

````
You are the script writer for a daily AI news bulletin. Write a script for
the anchor to read aloud.

## TODAY'S RAW MATERIAL
<paste headlines, links, article text, or your own notes here>

## MY ANGLE
<one sentence: the take you want the episode to land. This is mandatory —
if I leave it blank, ask me for it before writing.>

## OUTPUT SPEC
- Total: 210-225 words (90 seconds at broadcast pace)
- 3 stories, ranked by importance, not by order given
- Written for the EAR, not the eye

## STRUCTURE (follow exactly)

[HOOK — 12 words max]
The single most surprising concrete fact of the day. No greeting, no
"welcome back", no "today in AI". Start mid-punch.

[STORY 1 — 60 words]
What happened (1 sentence). Why it matters (1 sentence). What it changes
for a working developer or founder (1 sentence).

[STORY 2 — 50 words]
Same shape, tighter.

[STORY 3 — 45 words]
Same shape, tightest.

[THE TAKE — 40 words]
My angle above, argued. Connect at least two of the three stories into one
observation nobody else is making. This is the part that must not read like
a summary.

[SIGN-OFF — 8 words]
Consistent CTA.

## HARD RULES
- Short sentences. Max 18 words. One idea per sentence.
- Spell numbers as spoken: "four point five billion" not "$4.5B"
- Spell acronyms as read: "A-P-I", "L-L-M", "G-P-U"
- No em-dashes, no parentheses, no semicolons — the voice engine mangles them
- Use "..." for a deliberate beat before a punchline
- Zero hype adjectives: no "game-changing", "revolutionary", "insane", "wild"
- Never state a number, benchmark, or funding figure that is not in my raw
  material. If a detail is missing, write [VERIFY] and continue.
- Do not give financial, legal, medical, or political advice in any form.
  Report what happened. Do not tell the viewer what to do about it.

## ALSO RETURN
1. **B-roll cue sheet** — which of my 15 library clips to use at which
   timestamp
2. **Title** — under 60 characters, no clickbait, contains the key entity
3. **Description** — 3 lines + source links
4. **Hashtags** — 5, mixed reach
5. **On-screen text** — 4 short overlays with timestamps
6. **Word count + estimated runtime**
````

### Weekly Deep Dive variant

Same prompt, swap the spec:

```
- Total: 900-1,100 words (6-7 minutes)
- ONE story, examined in depth
- Structure: Hook (15w) → What happened (150w) → Background: how we got
  here (250w) → The mechanism: how it actually works (250w) → Who wins,
  who loses (200w) → My take (150w) → Sign-off
- Include one place where I explicitly say "I could be wrong about this,
  and here's what would change my mind"
```

> That last line is not decoration. Visible editorial judgment and stated
> uncertainty are the clearest human-authorship signals a reviewer can see.

---

## 5. Credit Budget

Assumes 22 daily bulletins + 4 weekly deep dives per month.

### HeyGen — Creator plan, 600 credits/month

| Use | Rate | Volume | Credits |
|---|---|---|---|
| Daily bulletin, Avatar III | ~3/min | 22 × 1.5 min | **99** |
| Weekly deep dive, Avatar III | ~3/min | 4 × 6 min | **72** |
| Hero moments, Avatar IV | ~20/min | 4 × 1.5 min | **120** |
| Re-renders / mistakes (20% buffer) | — | — | **58** |
| **Total** | | | **349 / 600** ✅ |

**42% headroom.** Avatar III is the workhorse; Avatar IV is reserved for launch, milestones, and any episode you expect to travel.

### ElevenLabs — Pro, 500,000 credits/month

| Use | Chars | Volume | Credits |
|---|---|---|---|
| Daily bulletin | ~1,300 | 22 | 28,600 |
| Weekly deep dive | ~5,500 | 4 | 22,000 |
| Retakes (assume 2× everything) | — | — | 50,600 |
| **Total** | | | **~101,000 / 500,000** ✅ |

**80% headroom.** You can afford multiple takes on every single line. Use it — the read quality is where amateur channels lose.

### Veo — Google AI Pro, 1,000 Flow credits/month

| Use | Credits |
|---|---|
| Initial B-roll library (one-time) | 150 |
| Monthly library refresh (5 new clips) | 50 |
| Weekly deep-dive custom visuals (2/week, Fast) | 160 |
| **Total ongoing** | **~210 / 1,000** ✅ |

Massive headroom. Bank the surplus into building a richer B-roll library each month.

---

## 6. Optional: n8n Research Assist

You write the editorial. n8n just puts the raw material on your desk by 7:00 AM.

```
Schedule Trigger (06:30 IST daily)
  ↓
RSS Feed Read × 6  ──  anthropic.com/news · openai.com/blog
                       deepmind.google/discover · techcrunch.com/category/artificial-intelligence
                       theverge.com/ai-artificial-intelligence · venturebeat.com/ai
  ↓
HTTP Request  ──  https://hacker-news.firebaseio.com/v0/topstories.json
  ↓
HTTP Request (batch)  ──  /v0/item/{id}.json  → filter score > 100
  ↓
Code node  ──  dedupe by title similarity, drop anything > 24h old,
               rank by (source_weight × recency × engagement)
  ↓
AI Agent (Claude)  ──  "Summarise the top 8 in one line each. For each, add
                        a one-line 'why this might matter'. Do NOT write a
                        script. Do NOT pick an angle. That's my job."
  ↓
Send to Slack / Email / Telegram
```

**Deliberate design:** the agent produces a *shortlist with neutral summaries*, never a script and never an angle. You pick the 3 and decide the take. That boundary is what keeps the channel human-authored — and it's also just better content.

---

## 7. Per-Episode Compliance Checklist

Run before every publish. Two minutes.

- [ ] Episode contains a **stated opinion or argument**, not only a summary
- [ ] The Take connects ≥2 stories into an original observation
- [ ] Format differs meaningfully from the last 3 episodes (structure, pacing, or a different segment type)
- [ ] No health, legal, financial, or political **advice** — reporting only
- [ ] Anchor is not presented with credentials, titles, or expert framing
- [ ] Every number/benchmark/figure traced to a source in the description
- [ ] No `[VERIFY]` tags left in the final script
- [ ] Sources linked in description
- [ ] YouTube Studio → **"Altered or synthetic content"** disclosure toggled ON
- [ ] Cuts to B-roll at least every 12 seconds
- [ ] One upload today, not two

### Why these rules exist

| Risk | Reality |
|---|---|
| Mass-produced / templated content | The Jan 2026 enforcement wave terminated 16 channels totalling ~35M subscribers and 4.7B views |
| Channel-wide penalty | Enforcement applies to the whole channel — one bad pattern can demonetize everything |
| AI personas on sensitive topics | July 2026 policy addition: AI personas delivering health, legal, financial, or political information are ineligible for monetization |
| Using AI at all | **Not a violation.** AI inside an original production with real scripts and real editorial decisions stays eligible |
| Disclosure | Toggling the synthetic-content label does not by itself reduce reach or monetization |

**Safe zone:** AI product launches, model releases, research papers, benchmarks, company/industry news, developer tooling.
**Danger zone:** AI regulation debates, "which AI stock to buy", "is AI coming for your job" advice, AI in medicine framed as guidance.

---

## 8. Publishing Specs

| Platform | Aspect | Length | Captions | Notes |
|---|---|---|---|---|
| YouTube Shorts | 9:16 | ≤ 90s | Burned-in | Title < 60 chars, `#Shorts` |
| YouTube long-form | 16:9 | 5–8 min | Auto + burned | Chapters, custom thumbnail |
| Instagram Reels | 9:16 | ≤ 90s | Burned-in | First 3s decide everything |
| TikTok | 9:16 | ≤ 90s | Burned-in | Trending audio at −30 dB under voice |
| LinkedIn | 1:1 or 16:9 | ≤ 60s | Burned-in | Best B2B reach for AI topics |
| X | 16:9 | ≤ 60s | Burned-in | Thread the sources under the post |

**Thumbnail formula (long-form):** anchor face left third + 3–4 word claim right + one accent colour. Same layout every week — build recognition.

---

## 9. 30-Day Launch Calendar

| Days | Goal | Output |
|---|---|---|
| **1–2** | Phase 0 setup | Anchor face, voice, HeyGen avatars, B-roll library, brand kit |
| **3–5** | Dry runs | 3 unpublished episodes. Fix pipeline friction. Time yourself. |
| **6–7** | Channel setup | Banner, about, playlists, handle, IG + TikTok accounts |
| **8–14** | Soft launch | 5 daily bulletins + 1 deep dive. Publish, don't promote. |
| **15–21** | Iterate | Read retention graphs. Where do people drop? Fix that exact second. |
| **22–30** | Push | Full cadence + n8n research assist live. Start cross-posting everywhere. |

### Success gates

| Metric | Day 30 target | Read as |
|---|---|---|
| Shorts avg view % | > 60% | Hook works |
| Long-form avg duration | > 3 min | Editorial has substance |
| Subs from Shorts | > 100 | Format resonates |
| Production time | < 45 min/day | Pipeline is sustainable |
| Policy strikes | 0 | Compliance holding |

**If production time is still > 60 min/day at Day 30, cut to 3 bulletins/week.** Burnout kills more of these channels than the algorithm does.

---

# PHASE B — Live Interactive Anchor (Roadmap)

**Trigger to start: 1,000 subscribers OR 30 consecutive days of Phase A shipping.**
Not before. A live anchor with no audience is a demo, not a product.

## B.1 What it is

Viewer visits your site, clicks "Ask the anchor", and has a real-time video conversation with the same face and voice from the daily broadcast — about today's stories specifically.

**Why it's the moat:** every faceless AI news channel can render a talking head. Almost none can let you *interrogate* the anchor. That's the thing that gets written about.

## B.2 Architecture

```
Browser (WebRTC)
    ↓
Simli — face rendering only, ~$0.05/min, sub-300ms latency
    ↕
ElevenLabs Agents — voice in/out (1,238 min/mo already included in your Pro plan)
    ↕
Claude — the brain, with today's stories as knowledge base
    ↕
Vector store (today's 3 stories + last 30 days of scripts)
```

**Why Simli over Tavus:** Simli is rendering-only, so you plug in the ElevenLabs voice you already pay for. Tavus bundles the whole stack at roughly $0.37/min overage and charges a 30-second minimum per conversation — you'd be paying twice for a voice you own.

## B.3 Tool comparison

| Tool | Free to start | Rate | Model |
|---|---|---|---|
| **Simli** ⭐ | $10 signup + 50 min/mo | ~$0.05/min | Rendering only, BYO LLM + TTS |
| Hedra Live Avatar | — | ~$0.05/min | LiveKit Agents, BYO stack |
| Tavus CVI | Free eval tier | $59/mo → 100 min, $0.37/min over | Full bundled stack |
| Beyond Presence / Anam | Demo | Higher | Bundled, managed |

## B.4 Build milestones

| # | Milestone | Time | Gate |
|---|---|---|---|
| B1 | Simli account, clone anchor face to a live avatar | 1 day | Face matches broadcast |
| B2 | ElevenLabs Agent with same voice, tested text-only | 2 days | Voice matches broadcast |
| B3 | Daily story knowledge base — auto-fed from published scripts | 3 days | Anchor knows today's episode |
| B4 | Web app (Lovable or Vercel) — story cards + "Ask" button | 4 days | Loads under 2s |
| B5 | Wire Simli + Agent + Claude over WebRTC | 5 days | End-to-end latency < 800ms |
| B6 | Guardrails + session caps | 2 days | See B.5 |
| B7 | Soft launch — CTA in daily episode outro | — | Track conversion |

## B.5 Guardrails (non-negotiable before public launch)

| Risk | Control |
|---|---|
| Runaway cost | Hard cap: 3 min/session, 20 sessions/day, kill switch at daily spend limit |
| Hallucinated news | System prompt: answer **only** from the story knowledge base. Unknown → "I haven't covered that." |
| Sensitive-topic drift | Refuse medical, legal, financial, political advice explicitly. Same rule as broadcast. |
| Anchor claims to be human | Persistent on-screen "AI anchor" label + it says so if asked |
| Abuse / prompt injection | Rate limit per IP, input length cap, no tool access |
| Idle burn | Auto-hangup on 15s silence |

**Cost model at launch scale:** 20 sessions/day × 2 min avg = 40 min/day = ~1,200 min/month.
- Simli rendering: ~$60/month
- ElevenLabs Agents: 1,238 min included in Pro → **$0**
- Claude API: ~$15/month
- **Total ≈ $75/month.** Do not start this until Phase A justifies it.

## B.6 Phase B success gates

- Session completion rate > 50%
- Avg session > 90 seconds
- Zero hallucinated facts across a manual audit of 20 transcripts
- Traffic from episode CTA > 2% of views

---

## Appendix A — Daily Checklist (print this)

```
□ Read n8n shortlist
□ Pick 3 stories
□ Write MY ANGLE in one sentence      ← non-delegable
□ Run Master Prompt
□ Hand-edit script (always)
□ Check for [VERIFY] tags
□ Render voice — ElevenLabs
□ Render video — HeyGen, Avatar III
□ Assemble in CapCut, cut every 8-12s
□ Burn captions
□ Compliance checklist (§7)
□ Upload + synthetic content disclosure ON
□ Cross-post: Shorts, Reels, TikTok, LinkedIn
□ Log: title, angle, views@24h
```

## Appendix B — Quick Reference

| Item | Value |
|---|---|
| Broadcast pace | 2.5 words/second |
| 60 sec | 150 words |
| 90 sec | 225 words |
| 6 min | ~900 words |
| Veo clip length | 8 sec max per generation |
| HeyGen Avatar III | ~3 credits/min |
| HeyGen Avatar IV | ~20 credits/min |
| ElevenLabs | ~1,000 credits ≈ 1 min speech |
| Hedra Character-3 | ~6 credits/sec @ 720p |
| Simli / Hedra Live | ~$0.05/min |

## Appendix C — Cost Ladder

| Stage | Monthly |
|---|---|
| Phase A launch | **$29** (HeyGen Creator only) |
| Phase A + Hedra hero episodes | $44 |
| Phase A + Phase B live anchor | ~$104 |
| Already owned (ElevenLabs Pro + Google AI Pro) | sunk |

---

*Pricing and platform policies verified July 2026. Re-check HeyGen credit rates and YouTube monetization policy quarterly — both changed materially in the last 12 months.*
