import {
  CheckCircle2,
  Cloud,
  Database,
  EyeOff,
  KeyRound,
  RadioTower,
  Save,
  Server,
  ShieldCheck,
  Volume2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useDesk } from "../DeskContext";
import { PageHeader } from "../components/PageHeader";
import { StatusChip } from "../components/StatusChip";

interface Preferences {
  autoPollRuns: boolean;
  confirmPublish: boolean;
  compactScript: boolean;
}

const defaultPreferences: Preferences = {
  autoPollRuns: true,
  confirmPublish: true,
  compactScript: false,
};

const providers = [
  {
    name: "Editorial model",
    role: "Structured script drafting",
    env: "ANTHROPIC_API_KEY",
    optional: true,
    icon: RadioTower,
    fallback: "Demo draft",
  },
  {
    name: "ElevenLabs",
    role: "Broadcast voice generation",
    env: "ELEVENLABS_API_KEY",
    optional: true,
    icon: Volume2,
    fallback: "Kokoro / local TTS",
  },
  {
    name: "Cloudflare R2",
    role: "Rendered media storage",
    env: "R2_ACCESS_KEY_ID",
    optional: true,
    icon: Cloud,
    fallback: "Local filesystem",
  },
  {
    name: "Kaggle",
    role: "GPU render execution",
    env: "KAGGLE_USERNAME",
    optional: true,
    icon: Server,
    fallback: "Manual notebook run",
  },
];

export function SettingsPage() {
  const { mode, notify } = useDesk();
  const [preferences, setPreferences] = useState<Preferences>(() => {
    try {
      const stored = localStorage.getItem("giani.signal-desk.preferences");
      return stored ? (JSON.parse(stored) as Preferences) : defaultPreferences;
    } catch {
      return defaultPreferences;
    }
  });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!saved) return;
    const timeout = window.setTimeout(() => setSaved(false), 2_000);
    return () => window.clearTimeout(timeout);
  }, [saved]);

  const savePreferences = () => {
    try {
      localStorage.setItem(
        "giani.signal-desk.preferences",
        JSON.stringify(preferences),
      );
      setSaved(true);
      notify("Desk preferences saved in this browser.", "success");
    } catch {
      notify("Browser storage is unavailable. Preferences were not saved.", "error");
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Desk configuration"
        title="Connect providers without exposing secrets."
        description="The browser only knows the API base URL. Provider credentials belong in the backend environment."
        action={
          <button
            type="button"
            className="button button-primary"
            onClick={savePreferences}
          >
            {saved ? <CheckCircle2 size={17} /> : <Save size={17} />}
            {saved ? "Saved" : "Save preferences"}
          </button>
        }
      />

      <section className="security-banner">
        <div className="security-icon">
          <EyeOff size={24} />
        </div>
        <div>
          <p className="eyebrow">Secret-safe boundary</p>
          <h2>No provider key is displayed, stored, or requested here.</h2>
          <p>
            Add credentials to the backend process or secret manager. Never prefix a
            provider secret with <code>VITE_</code>; that would ship it to the browser.
          </p>
        </div>
        <ShieldCheck size={32} />
      </section>

      <div className="settings-grid">
        <section className="panel connection-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Frontend connection</p>
              <h2>Newsroom API</h2>
            </div>
            <StatusChip status={mode} />
          </div>
          <dl className="connection-list">
            <div>
              <dt>Resolved base URL</dt>
              <dd><code>{api.baseUrl}</code></dd>
            </div>
            <div>
              <dt>Browser variable</dt>
              <dd><code>VITE_API_URL</code></dd>
            </div>
            <div>
              <dt>Default</dt>
              <dd><code>/api</code></dd>
            </div>
            <div>
              <dt>Fallback behavior</dt>
              <dd>Clearly labeled local demo state</dd>
            </div>
          </dl>
          <div className="config-example">
            <span>.env.local</span>
            <code>VITE_API_URL=http://127.0.0.1:8000/api</code>
          </div>
        </section>

        <section className="panel preferences-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Local behavior</p>
              <h2>Desk preferences</h2>
            </div>
            <Database size={20} />
          </div>
          <div className="toggle-list">
            <label>
              <div>
                <strong>Auto-poll active runs</strong>
                <span>Refresh running jobs every three seconds.</span>
              </div>
              <input
                type="checkbox"
                role="switch"
                checked={preferences.autoPollRuns}
                onChange={(event) =>
                  setPreferences((current) => ({
                    ...current,
                    autoPollRuns: event.target.checked,
                  }))
                }
              />
            </label>
            <label>
              <div>
                <strong>Confirm publish package</strong>
                <span>Keep a deliberate human checkpoint before delivery.</span>
              </div>
              <input
                type="checkbox"
                role="switch"
                checked={preferences.confirmPublish}
                onChange={(event) =>
                  setPreferences((current) => ({
                    ...current,
                    confirmPublish: event.target.checked,
                  }))
                }
              />
            </label>
            <label>
              <div>
                <strong>Compact script editor</strong>
                <span>Use shorter fields for dense editorial review.</span>
              </div>
              <input
                type="checkbox"
                role="switch"
                checked={preferences.compactScript}
                onChange={(event) =>
                  setPreferences((current) => ({
                    ...current,
                    compactScript: event.target.checked,
                  }))
                }
              />
            </label>
          </div>
        </section>
      </div>

      <section className="provider-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Optional backend providers</p>
            <h2>Production integrations</h2>
          </div>
          <p>Names only. Secret values stay server-side.</p>
        </div>
        <div className="provider-grid">
          {providers.map(({ name, role, env, optional, icon: Icon, fallback }) => (
            <article className="provider-card" key={name}>
              <div className="provider-icon">
                <Icon size={21} />
              </div>
              <span>{optional ? "OPTIONAL" : "REQUIRED"}</span>
              <h3>{name}</h3>
              <p>{role}</p>
              <div className="env-name">
                <KeyRound size={14} />
                <code>{env}</code>
              </div>
              <small>Fallback: {fallback}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="settings-footnote">
        <ShieldCheck size={20} />
        <div>
          <strong>Recommended production pattern</strong>
          <p>
            Browser → authenticated backend API → provider SDK. Keep logs free of raw
            credentials and rotate keys from the provider console or a managed secret
            store.
          </p>
        </div>
      </section>
    </div>
  );
}
