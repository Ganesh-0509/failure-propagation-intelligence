import { useState } from "react";
import { NAV_ITEMS } from "../nav";
import type { ViewId } from "../nav";

interface Props {
  view: ViewId;
  onNavigate: (v: ViewId) => void;
}

/**
 * Fixed left navigation. On narrow screens (<900px, via CSS) it collapses to a
 * top bar with a hamburger that toggles the nav list.
 */
export function Sidebar({ view, onNavigate }: Props) {
  const [open, setOpen] = useState(false);

  const go = (v: ViewId) => {
    onNavigate(v);
    setOpen(false); // close the mobile menu after picking a view
  };

  return (
    <nav className={`sidebar ${open ? "sidebar--open" : ""}`} aria-label="Primary">
      <div className="sidebar__brand">
        <span className="sidebar__logo">FPI</span>
        <div className="sidebar__brand-text">
          <span className="sidebar__name">Failure Propagation</span>
          <span className="sidebar__sub">Intelligence · technician tool</span>
        </div>
        <button
          className="sidebar__hamburger"
          aria-label="Toggle navigation"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <span aria-hidden>{open ? "✕" : "☰"}</span>
        </button>
      </div>

      <ul className="nav">
        {NAV_ITEMS.map((item) => (
          <li key={item.id}>
            <button
              className={`nav__item ${item.id === view ? "nav__item--active" : ""}`}
              onClick={() => go(item.id)}
              aria-current={item.id === view ? "page" : undefined}
            >
              <span className="nav__label">{item.label}</span>
              <span className="nav__hint">{item.hint}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
