import {
  Aperture,
  CheckCircle2,
  Film,
  Image,
  MonitorCheck,
  Ratio,
} from "lucide-react";
import { useState } from "react";
import { brollSlots } from "../demo";
import { PageHeader } from "../components/PageHeader";

export function LibraryPage() {
  const [anchorLoaded, setAnchorLoaded] = useState(false);
  const [anchorFailed, setAnchorFailed] = useState(false);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Canonical media library"
        title="One identity. Fifteen visual beats."
        description="Locked brand assets and numbered B-roll slots keep every edition recognizable."
      />

      <section className="library-hero">
        <article className="canonical-anchor-card">
          <div className="canonical-image">
            <img
              src="/anchor/mira-anchor-vertical.png"
              alt="Canonical portrait of Mira"
              onLoad={() => setAnchorLoaded(true)}
              onError={() => setAnchorFailed(true)}
            />
            <span className="asset-badge">CANONICAL / DO NOT REPLACE</span>
          </div>
          <div className="canonical-copy">
            <p className="eyebrow">Anchor identity / A-01</p>
            <h2>Mira — Vertical</h2>
            <p>
              Front-facing broadcast portrait with locked wardrobe, set lighting, and
              neutral AI Desk title.
            </p>
            <div className="asset-spec-grid">
              <div>
                <Ratio size={18} />
                <span>Aspect</span>
                <strong>9:16</strong>
              </div>
              <div>
                <Aperture size={18} />
                <span>Framing</span>
                <strong>Head + shoulders</strong>
              </div>
              <div>
                <MonitorCheck size={18} />
                <span>Asset check</span>
                <strong>
                  {anchorFailed ? "Missing" : anchorLoaded ? "Passed" : "Checking…"}
                </strong>
              </div>
            </div>
            <div className={anchorFailed ? "asset-path failed" : "asset-path"}>
              {anchorFailed ? (
                <Image size={16} />
              ) : (
                <CheckCircle2 size={16} />
              )}
              <code>/anchor/mira-anchor-vertical.png</code>
            </div>
          </div>
        </article>

        <article className="library-rule-card">
          <span>IDENTITY RULE 01</span>
          <blockquote>
            “Recognition is built by repetition, not reinvention.”
          </blockquote>
          <p>
            Keep Mira’s name, face, neutral title, voice, studio set, and sign-off
            consistent across every daily bulletin.
          </p>
          <dl>
            <div>
              <dt>Display name</dt>
              <dd>Mira</dd>
            </div>
            <div>
              <dt>Neutral title</dt>
              <dd>AI Desk</dd>
            </div>
            <div>
              <dt>Sign-off</dt>
              <dd>Keep your signal clean.</dd>
            </div>
          </dl>
        </article>
      </section>

      <section className="broll-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Reusable motion library</p>
            <h2>15 B-roll slots</h2>
          </div>
          <div className="slot-legend">
            <span><i className="ready" /> Prompt defined</span>
            <span><i /> Media file optional</span>
          </div>
        </div>
        <div className="broll-grid">
          {brollSlots.map((name, index) => (
            <article className="broll-card" key={name}>
              <div className="broll-frame">
                <div className={`broll-art art-${(index % 5) + 1}`}>
                  <Film size={25} strokeWidth={1.5} />
                  <span>{String(index + 1).padStart(2, "0")}</span>
                </div>
                <span className="slot-status">SLOT READY</span>
              </div>
              <div>
                <span>B–{String(index + 1).padStart(2, "0")}</span>
                <h3>{name}</h3>
                <p>8 sec · reusable · editorial cue</p>
              </div>
            </article>
          ))}
        </div>
        <p className="library-footnote">
          Slot readiness means the canonical prompt and edit position are defined. Add
          generated or licensed media files to the backend asset store when available;
          the desk does not claim missing files exist.
        </p>
      </section>
    </div>
  );
}
