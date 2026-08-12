/** App shell: sidebar navigation, mobile header, and the page slot. */

import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { to: "/", label: "Dashboard", end: true, icon: IconGrid },
  { to: "/progress", label: "Progress", icon: IconChart },
  { to: "/log", label: "Log workout", icon: IconPlus },
  { to: "/coach", label: "AI Coach", icon: IconSpark },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-ink-950">
      {/* Backdrop, mobile only. */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-ink-800 bg-ink-900 transition-transform lg:static lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center gap-2.5 border-b border-ink-800 px-5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-sm font-bold text-ink-950">
            L
          </div>
          <span className="text-sm font-semibold tracking-tight">LiftSync</span>
        </div>

        <nav className="flex-1 space-y-0.5 p-3">
          {NAV.map(({ to, label, end, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setMobileOpen(false)}
              // NavLink hands you isActive, so the current page can be
              // highlighted without tracking the route yourself.
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-ink-800 font-medium text-ink-100"
                    : "text-ink-400 hover:bg-ink-850 hover:text-ink-200"
                }`
              }
            >
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-ink-800 p-3">
          <div className="flex items-center gap-3 rounded-lg px-3 py-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-700 text-xs font-semibold text-ink-200">
              {(user?.display_name || "?").charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium text-ink-200">
                {user?.display_name}
              </div>
              <div className="truncate text-[11px] text-ink-400">{user?.email}</div>
            </div>
          </div>
          <button
            onClick={logout}
            className="mt-1 w-full rounded-lg px-3 py-2 text-left text-xs text-ink-400 transition-colors hover:bg-ink-850 hover:text-ink-200"
          >
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-ink-800 px-4 lg:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            className="rounded-lg p-2 text-ink-300 hover:bg-ink-800"
            aria-label="Open navigation"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M4 6h16M4 12h16M4 18h16"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <span className="text-sm font-semibold">LiftSync</span>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto max-w-6xl">
            {/* Outlet is where react-router renders the current page. */}
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

function IconGrid() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 4h6v6H4V4Zm10 0h6v6h-6V4ZM4 14h6v6H4v-6Zm10 0h6v6h-6v-6Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconChart() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 19V5m0 14h16M8 15l3.5-4 3 2.5L20 7"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconPlus() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 5v14M5 12h14"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconSpark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3ZM18 15l.9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9L18 15Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}
