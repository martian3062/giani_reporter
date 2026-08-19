# AI News Anchor — $0 Stack (Fully Self-Owned)

**Companion to:** `AI-News-Anchor-Build-Plan.md` (format, script prompt, compliance, calendar — all still apply)
**This doc replaces:** the infrastructure layer only
**Constraint:** every component either free forever, or already paid for, and nothing sitting on an account you don't control

---

## 0. What Changed

| Layer | Paid plan | **Free replacement** | Why it works |
|---|---|---|---|
| Orchestration | n8n Cloud (someone else's) | **Your own n8n, self-hosted on Oracle Always Free** | Community Edition = unlimited executions, $0 |
| Anchor face | HeyGen Creator $29/mo | **Veo base loop + LatentSync on Kaggle GPU** | You already own Veo; Kaggle GPU is free |
| Voice | ElevenLabs Pro | **Keep it** (already owned) — fallback: Kokoro / XTTS-v2 | Fallback if the sub ever lapses |
| Assembly | CapCut | **FFmpeg** | Scriptable, so the pipeline can run itself |
| Captions | CapCut auto | **faster-whisper** | Free, better timing, runs on the same GPU |
| Storage | — | **Git repo + Cloudflare R2 free tier** | Versioned, yours |

### **New monthly cost: $0.**

---

## 1. Orchestration — Three Options

| | **Self-hosted n8n** ⭐ | **Activepieces** | **GitHub Actions** |
|---|---|---|---|
| License | Sustainable Use (fair-code) | **MIT** — true open source | Free tier |
| Self-host free? | Yes, unlimited executions | Yes, unlimited | N/A — GitHub runs it |
| Learning curve | **Zero for you** — same tool as work | Low | Low if you're comfy in YAML |
| Server needed | Yes | Yes (Postgres + Redis) | **None** |
| Maintenance | Updates, backups, monitoring | Same | **Zero** |
| Best when | You want a visual builder you own | You want a permissive license | You want no infra at all |

### Recommendation: **your own n8n on Oracle Cloud Always Free**

Reasoning:
- You already build n8n workflows daily at work — zero learning cost, and it doubles as portfolio proof you can self-host and operate it, not just click nodes in someone else's tenant
- Self-hosting the Community Edition is free with no execution limits; the licence only restricts *reselling* n8n as a service, which you're not doing
- Oracle's Always Free tier gives up to **4 ARM cores and 24 GB RAM, and does not expire** — unlike AWS/Azure free tiers that die after 12 months

**Licence caveat, stated plainly:** n8n is fair-code, not OSI open source. Free for your own internal use forever. If you ever want to *sell* automation-as-a-service built on it, switch to Activepieces (MIT) then.

**Escape hatch:** if you don't want to maintain a server at all, GitHub Actions on a cron schedule does this entire pipeline in a Python script with zero infrastructure. Less pretty, genuinely zero ops.

---

## 2. The Core Technique — Veo Loop + LatentSync

This is the part that replaces $29/mo HeyGen, and it produces *better* results than photo-only animation.

### The problem with the naive free approach
Feeding a single still photo to SadTalker/Hallo produces stiff, uncanny motion. This is why people give up on free stacks and pay HeyGen.

### The fix: sync onto real motion instead of generating motion

```
1. Veo  ──→  ONE 8-second anchor idle loop (blinking, micro head movement,
             mouth neutral). Cost: 10 Flow credits. Generate ONCE.
                    ↓
2. FFmpeg ──→ ping-pong the loop → seamless, extend to any length
                    ↓
3. ElevenLabs ──→ voice track from your script
                    ↓
4. LatentSync ──→ lip-sync the voice onto the looped video  [Kaggle free GPU]
                    ↓
5. FFmpeg ──→ + B-roll cuts + burned captions + lower third
                    ↓
             90-second episode. Marginal cost: $0.
```

**Why this beats photo animation:** LatentSync is a *video-to-video* lip-sync model — it edits the mouth region of existing footage. Give it real footage with real idle motion and it only has to solve the mouth. Give it a static image and it has to invent everything, which is where the uncanny valley lives.

### Veo prompt for the base loop

```
Medium close-up of a [description] news presenter seated at a modern
news desk, looking directly at camera, neutral professional expression,
mouth closed, subtle natural blinking and very slight head movement,
soft three-point studio lighting, dark blue-grey background with soft
bokeh, static locked-off camera, no camera movement, 4K, photorealistic
```

**Critical requirements:**
- `static locked-off camera, no camera movement` — a moving camera breaks the loop
- `mouth closed` — LatentSync overwrites the mouth anyway; a closed start is cleanest
- Generate **5–8 candidates**, pick the one with the least head drift
- Save the prompt + seed. This is your anchor's canonical footage.

Generate a 16:9 and a 9:16 version. Total cost: ~80 Flow credits out of your 1,000/month.

### Model choice for the sync step

| Model | Use when | GPU need |
|---|---|---|
| **LatentSync 1.6** ⭐ | Default. Best visual fidelity, strong identity preservation | T4 works; A10/4090 faster |
| **MuseTalk** | Speed matters, or LatentSync artifacts on your face | Lighter |
| **Wav2Lip** | Fallback. Best raw sync accuracy, worst pixels | Runs on almost anything |

Start with LatentSync. If your specific anchor face produces jaw artifacts, drop to MuseTalk. Route per-face, not per-principle.

---

## 3. Free GPU — Kaggle

| Platform | Free quota | Session | Reliability |
|---|---|---|---|
| **Kaggle** ⭐ | **30 hrs/week**, T4 or P100 (16 GB) | Up to 9–12 hrs | **Fixed, visible quota** |
| Google Colab | 15–30 hrs/week, T4 | ~12 hrs | Dynamic — can throttle without warning |
| HF ZeroGPU Spaces | Limited quota, shared H200 | Per-request | Good for a hosted demo |
| Lightning AI | ~80 hrs/month | Persistent workspace | Phone verification |

### Use Kaggle. Two reasons:
1. **The quota is visible and fixed.** Colab's is dynamically allocated — your session can die mid-render with no counter telling you why. For a daily deadline that's disqualifying.
2. **30 hrs/week is absurdly more than you need.** A 90-second LatentSync render on a T4 is roughly 8–15 minutes. Daily = ~7 hrs/month. You're using under 6% of the free quota.

**Backup:** keep a Colab notebook with the identical setup. If Kaggle queues are long on a deadline day, switch. Combined you have 45–60 free GPU hours/week.

> Oracle/Kaggle both want a card for identity verification. Oracle rejects virtual, prepaid, and PIN-debit cards — use a real credit card. You will not be charged inside Always Free limits, but **set a budget alert on day one** anyway.

---

## 4. Free Tool Matrix (per layer)

### Script → Voice
| Need | Primary | Free fallback |
|---|---|---|
| Script | Claude | — |
| TTS | **ElevenLabs Pro** (owned) | **Kokoro-82M** (tiny, fast, great quality), XTTS-v2, F5-TTS, Piper, Chatterbox |

Kokoro is the one to test — it's small enough to run on CPU and the quality is startlingly close to commercial TTS. Build the fallback path now so an expiring subscription never stops the channel.

### Visuals
| Need | Primary | Free fallback |
|---|---|---|
| Anchor base loop | **Veo** (owned) | Wan 2.x, LTX-Video, HunyuanVideo on Kaggle |
| Anchor still (if needed) | Nano Banana / Flux | Flux.1-dev, Qwen-Image, SDXL on Kaggle |
| B-roll (15-clip library) | **Veo** (owned) | Same open models, or Pexels/Pixabay stock |
| Lip-sync | **LatentSync** on Kaggle | MuseTalk → Wav2Lip |

If you ever drop Google AI Pro: **non-subscribers get 50 free Flow credits per day**, refreshed on first use (they don't roll over). That's ~5 Veo 3.1 Lite generations daily, free, forever. More than enough to maintain a B-roll library.

> **Do not upgrade or change your Google AI plan mid-month** — any remaining free Flow credits are forfeited immediately on upgrade.

### Assembly & publish
| Need | Tool |
|---|---|
| Edit / concat / crop / burn | **FFmpeg** |
| Captions | **faster-whisper** (word-level timestamps) |
| Manual polish | CapCut Desktop (free) |
| Storage | Git LFS or Cloudflare R2 free tier |
| Thumbnails | GIMP / Canva free / Flux on Kaggle |

---

## 5. Architecture

```
┌─ ORACLE CLOUD ALWAYS FREE (ARM VM, 24 GB) ─────────────┐
│                                                         │
│   n8n (Docker)          ← YOUR instance, your data      │
│    │                                                    │
│    ├─ 06:30 cron → RSS × 6 + Hacker News API            │
│    ├─ dedupe + rank (Code node)                         │
│    ├─ Claude → neutral shortlist (NO angle, NO script)  │
│    └─ → Telegram/Email to you                           │
│                                                         │
│   YOU pick 3 stories + write THE ANGLE                  │
│    │                                                    │
│    ├─ Master Prompt → script                            │
│    └─ hand-edit                                         │
│                                                         │
│   n8n → ElevenLabs API → voice.mp3 → R2                 │
│    └─ trigger Kaggle render (see §6)                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─ KAGGLE (free T4, 30 hrs/wk) ──────────────────────────┐
│   pull voice.mp3 + anchor_loop.mp4                      │
│   → LatentSync → anchor_synced.mp4                      │
│   → faster-whisper → subs.srt                           │
│   → FFmpeg: B-roll cuts, captions, lower third          │
│   → push final.mp4 back to R2                           │
└─────────────────────────────────────────────────────────┘
                          ↓
              Review → Upload → Disclosure toggle ON
```

**Kaggle has no inbound webhook.** Two ways to bridge:
- **Simple (start here):** open the notebook, hit Run All. 30 seconds of your day.
- **Automated (later):** Kaggle API — `kaggle kernels push` from n8n, poll `kernels status`, then `kernels output` to pull the file. Fully hands-off.

---

## 6. Setup — One Time

### 6.1 Oracle Cloud VM (~30 min)
1. cloud.oracle.com → sign up (real credit card, ID verification only)
2. Region: **choose one close to you and stick with it** — Always Free capacity is per-region and Mumbai/Hyderabad fill up
3. Compute → Create Instance → Image **Ubuntu 22.04** → Shape **VM.Standard.A1.Flex**
4. Set **4 OCPU / 24 GB** (the whole Always Free ARM allocation)
5. Download the SSH private key **before** clicking Create — you cannot retrieve it later
6. Networking → Security List → add ingress on **5678**
7. Billing → **set a budget alert at $1** — belt and braces

If A1.Flex says "out of capacity", retry at off-peak hours or pick another region. This is normal and not a dead end.

### 6.2 n8n via Docker (~15 min)
```bash
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER && newgrp docker
mkdir ~/n8n && cd ~/n8n
```
`docker-compose.yml`:
```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n
    restart: always
    ports: ["5678:5678"]
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=<strong-password>
      - GENERIC_TIMEZONE=Asia/Kolkata
      - TZ=Asia/Kolkata
    volumes:
      - ./n8n_data:/home/node/.n8n
```
```bash
docker compose up -d
```
→ `http://<your-ip>:5678`

**Also do:** Ubuntu's `iptables` blocks ports independently of Oracle's security list. If the page won't load, that's why:
```bash
sudo iptables -I INPUT -p tcp --dport 5678 -j ACCEPT
sudo netfilter-persistent save
```

**Before going public:** put Caddy in front for automatic HTTPS. Basic auth over plain HTTP sends your password in the clear.

### 6.3 Kaggle render notebook (~1 hr)
1. kaggle.com → Account → **Phone verify** (required to unlock GPU)
2. New Notebook → Settings → Accelerator **GPU T4 ×2** → Internet **On**
3. Cells: install LatentSync → download weights → mount inputs → run sync → whisper → ffmpeg → save output
4. Upload `anchor_loop.mp4` as a **Kaggle Dataset** — persists across sessions, no re-upload
5. **Save a Version** so the setup cells are cached

Budget 1 hour for first-time dependency wrangling. After that it's Run All.

---

## 7. FFmpeg Recipes

```bash
# Ping-pong an 8s Veo clip into a seamless loop
ffmpeg -i base.mp4 -filter_complex \
  "[0:v]reverse[r];[0:v][r]concat=n=2:v=1[v]" -map "[v]" loop.mp4

# Extend the loop to match voice duration (e.g. 92s)
ffmpeg -stream_loop -1 -i loop.mp4 -t 92 -c copy anchor_bed.mp4

# Mux the synced anchor with voice
ffmpeg -i anchor_synced.mp4 -i voice.mp3 \
  -c:v copy -c:a aac -shortest anchor_final.mp4

# Vertical 9:16 crop for Shorts/Reels/TikTok
ffmpeg -i anchor_final.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" vertical.mp4

# Cut to B-roll (replace 12s-17s, keep the voice underneath)
ffmpeg -i vertical.mp4 -i broll_03.mp4 -filter_complex \
  "[1:v]scale=1080:1920,setpts=PTS-STARTPTS+12/TB[b]; \
   [0:v][b]overlay=enable='between(t,12,17)'[v]" \
  -map "[v]" -map 0:a -c:a copy with_broll.mp4

# Burn captions
ffmpeg -i with_broll.mp4 -vf "subtitles=subs.srt:force_style=\
'FontName=Montserrat,FontSize=18,Bold=1,PrimaryColour=&HFFFFFF,\
OutlineColour=&H000000,BorderStyle=1,Outline=3,Alignment=2,MarginV=140'" \
  final.mp4
```

Wrap these in one `build.sh` and the whole assembly step becomes a single command.

---

## 8. Daily SOP — Free Version

| # | Step | Free stack | Paid stack |
|---|---|---|---|
| 1 | Review shortlist | 10 min | 10 min |
| 2 | Pick 3 + **write the angle** | 5 min | 5 min |
| 3 | Master Prompt → script | 3 min | 3 min |
| 4 | Hand-edit | 7 min | 7 min |
| 5 | Voice render | 3 min | 3 min |
| 6 | Anchor render | **12–18 min** (Kaggle queue + sync) | 5–8 min |
| 7 | Assembly | **2 min** (`./build.sh`) | 15 min (manual) |
| 8 | Compliance check | 2 min | 2 min |
| 9 | Publish | 10 min | 10 min |
| | **Total** | **~55–60 min** | ~55–60 min |

**The free stack is not slower day-to-day.** You lose time on the GPU render and win it back on scripted assembly. The real cost is **front-loaded setup: 1–2 full days.**

---

## 9. Honest Trade-offs

| | Free stack | HeyGen $29 |
|---|---|---|
| Monthly cost | **$0** | $29 |
| Setup time | **1–2 days** | 2 hours |
| Out-of-box quality | Good after tuning | **Consistently good immediately** |
| Failure mode | Kaggle queue, dependency breakage, model artifacts | Credit exhaustion |
| Control | **Total** | Vendor-dependent |
| Portfolio value | **High** — self-hosted infra + open models | Low |
| Debug burden | **Yours** | Theirs |
| Scales to daily? | Yes, comfortably | Yes |

**Where the free path genuinely loses:** HeyGen's Avatar III is trained, tuned, and consistent across faces. LatentSync on your particular anchor face may need a few evenings of parameter tuning before it stops producing jaw artifacts. Budget for that frustration.

**Where it genuinely wins, beyond cost:** you end up with a self-hosted automation server, an open-model inference pipeline, and a scripted render chain — all of which are portfolio artifacts in a way that "I have a HeyGen subscription" is not. Given you're a 2026 grad targeting ML/infra roles, that's not a small side benefit.

### Recommended sequence
1. **Week 1:** Build free. Ship 5 episodes. Learn where it breaks.
2. **If the render step is what's blocking you at Day 14** — and only that step — pay the $29. Keep everything else free.

Don't pay upfront to avoid a problem you haven't hit yet.

---

## 10. When to Actually Spend

| Trigger | Spend | Why |
|---|---|---|
| LatentSync artifacts survive 3 evenings of tuning | HeyGen Creator $29 | Buying quality, not convenience |
| Kaggle queue misses your publish window 3×/week | Colab Pro $9.99 | Cheapest reliability fix |
| Oracle A1 capacity never frees up in your region | Hetzner/Contabo VPS ~$5 | Or fall back to GitHub Actions |
| ElevenLabs sub lapses | $0 — switch to Kokoro | Fallback already built |
| Channel hits 1,000 subs | Phase B (§11) | Now there's an audience to justify it |

---

## 11. Phase B — Free Version

Same gate as before: **1,000 subs OR 30 consecutive days shipping.** Not sooner.

| Layer | Paid plan | Free / cheap path |
|---|---|---|
| Face rendering | Simli ~$0.05/min | Simli free tier: **$10 signup + 50 min/month** |
| Voice | ElevenLabs Agents | **1,238 min/mo already in your Pro plan** |
| Brain | Claude API | Free tiers: Groq, Cerebras, Gemini API |
| Frontend | Lovable | **Cloudflare Pages / Vercel Hobby** — free |
| Knowledge base | Vector DB | **SQLite + embeddings** on the same Oracle VM |
| Transport | — | LiveKit open source, self-hosted on the same VM |

**Free-tier ceiling:** Simli's 50 free min/month ≈ 25 two-minute conversations. Perfect for launch — enough to prove people want it, small enough that you can't get a surprise bill. Add a hard session cap in code anyway.

---

## Appendix — Free Stack Cheat Sheet

| Layer | Tool | Limit |
|---|---|---|
| Orchestration | Self-hosted n8n | Unlimited executions |
| Server | Oracle Always Free ARM | 4 cores / 24 GB, never expires |
| GPU | Kaggle | 30 hrs/week, T4/P100 16 GB |
| GPU backup | Colab | 15–30 hrs/week |
| Lip-sync | LatentSync 1.6 | Free, open weights |
| TTS | ElevenLabs Pro (owned) | ~500 min/mo |
| TTS fallback | Kokoro-82M | Unlimited, local |
| Video gen | Veo (owned) | 1,000 Flow credits/mo |
| Video gen (no sub) | Veo via Flow | 50 credits/day free |
| Captions | faster-whisper | Unlimited, local |
| Assembly | FFmpeg | Unlimited |
| Live avatar (Phase B) | Simli | $10 + 50 min/mo free |
| Hosting | Cloudflare Pages | Free |

---

## First Three Actions

1. **Create the Oracle Cloud account today.** A1.Flex capacity in Indian regions is the single most likely thing to block you, and it can take a few days of retries. Start the clock now.
2. **Phone-verify Kaggle.** Two minutes, unlocks the GPU.
3. **Generate the Veo anchor loop.** 10 Flow credits, and it's the asset every single episode depends on. Get it right once.

---

*Verified July 2026. Free tiers move — re-check Oracle Always Free shapes, Kaggle quotas, and Flow credit rates quarterly.*
