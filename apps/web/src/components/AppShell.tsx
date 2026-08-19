import {
  Archive,
  AudioLines,
  CircleGauge,
  FlaskConical,
  Instagram,
  Menu,
  Plus,
  Radio,
  Settings,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useDesk } from "../DeskContext";
import { StatusChip } from "./StatusChip";
import { Toasts } from "./Toasts";

const navItems = [
  { to: "/", label: "Overview", icon: CircleGauge, end: true },
  { to: "/research", label: "Research", icon: FlaskConical },
  { to: "/studio", label: "Studio", icon: AudioLines },
  { to: "/posts", label: "Posts", icon: Instagram },
  { to: "/library", label: "Library", icon: Archive },
  { to: "/runs", label: "Runs", icon: Radio },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const { mode, overview } = useDesk();
  const [menuOpen, setMenuOpen] = useState(false);
  const [now, setNow] = useState(new Date());
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(interval);
  }, []);

  const dateLabel = now.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
  const timeLabel = now.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            G
          </div>
          <div>
            <span className="brand-name">GIANI</span>
            <span className="brand-subtitle">Signal Desk</span>
          </div>
          <button
            type="button"
            className="icon-button sidebar-close"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          >
            <X size={20} />
          </button>
        </div>

        <div className="edition-block">
          <span>Daily edition</span>
          <strong>{dateLabel}</strong>
          <small>Anchor / Mira</small>
        </div>

        <nav className="primary-nav" aria-label="Primary">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
              <span>{label}</span>
              {label === "Research" && overview.selected_count > 0 ? (
                <span className="nav-count">{overview.selected_count}</span>
              ) : null}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="signal-meter" aria-label="Daily workflow completion">
            <div>
              <span>Today’s rundown</span>
              <strong>{overview.selected_count}/3 locked</strong>
            </div>
            <div className="mini-bars" aria-hidden="true">
              {[0, 1, 2].map((index) => (
                <span
                  key={index}
                  className={index < overview.selected_count ? "filled" : ""}
                />
              ))}
            </div>
          </div>
          <p>Human judgment stays on the desk.</p>
        </div>
      </aside>

      {menuOpen ? (
        <button
          className="sidebar-scrim"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      ) : null}

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              <Menu size={21} />
            </button>
            <div className="mobile-wordmark">GIANI / SIGNAL DESK</div>
            <StatusChip status={mode} />
          </div>
          <div className="topbar-right">
            <span className="desk-clock">
              <b>{timeLabel}</b> IST
            </span>
            <button
              className="button button-primary button-compact"
              type="button"
              onClick={() => navigate("/studio")}
            >
              <Plus size={16} />
              New bulletin
            </button>
          </div>
        </header>

        <main id="main-content" className="main-content" tabIndex={-1}>
          <Outlet />
        </main>

        <nav className="mobile-nav" aria-label="Mobile primary">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                isActive ? "mobile-nav-link active" : "mobile-nav-link"
              }
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
      <Toasts />
    </div>
  );
}
