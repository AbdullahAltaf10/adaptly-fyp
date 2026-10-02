/**
 * The frame around every signed-in screen: a dashboard-style sidebar,
 * identity, sign out.
 *
 * This used to be a top navbar. Moved to a sidebar because that is what a
 * dashboard-shaped app - the shell around a session, a library, an analytics
 * view, and for HR a compliance list - actually calls for: scope's own
 * mockup (section 12) draws exactly this shape, a left-hand nav column next
 * to the content, not a single row of links above it. A sidebar also has
 * room to grow as more sections (Module 9's HR manual management, most
 * concretely) get added, where a top bar runs out of width first.
 *
 * Two things here are accessibility rather than decoration:
 *
 * - **A skip link.** The nav is the first thing in the tab order on every
 *   page; without a skip link a keyboard user tabs through it before reaching
 *   the content, on every navigation.
 * - **`aria-current="page"`.** The active item is styled, and styling alone
 *   does not tell a screen-reader user which one they are on.
 *
 * The sidebar keeps its icons and drops its labels to `sr-only` below `md` -
 * it never disappears or hides behind a menu button on a small screen, since
 * every item stays reachable and keyboard-focusable either way.
 */

import {
  BarChart3,
  BookOpen,
  GraduationCap,
  History,
  LayoutDashboard,
  Library,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Settings as SettingsIcon,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { signOut } from "firebase/auth";

import { auth } from "../auth/firebase";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/library", label: "My documents", icon: Library },
  { to: "/study", label: "Study session", icon: BookOpen },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/progress", label: "Your progress", icon: History },
];

/**
 * Shown only to corporate accounts. Scope 6.10 makes the attestation report a
 * corporate feature: an individual learner studying their own PDF has no
 * compliance context, so offering them the page puts a corporate concept in
 * front of the wrong user group. The page itself still works for whoever opens
 * it directly, and the backend is owner-only regardless - this is about not
 * advertising it.
 */
const CORPORATE_NAV = [{ to: "/compliance", label: "Compliance report", icon: ShieldCheck }];

/** Shown only to HR admins; the backend enforces the same rule. */
const HR_NAV = [{ to: "/hr/compliance", label: "HR compliance", icon: Users }];

function navClass({ isActive }) {
  return [
    "flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors duration-150",
    isActive
      ? "bg-accent text-on-accent"
      : "text-ink hover:bg-page",
  ].join(" ");
}

const SIDEBAR_COLLAPSED_KEY = "adaptly.sidebarCollapsed";

/** A per-viewer convenience (remembering a UI toggle), not state that must
 * persist reliably - so a private window or blocked storage just falls back
 * to the default (expanded) rather than breaking the page. */
function readStoredCollapsed() {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeStoredCollapsed(value) {
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, value ? "1" : "0");
  } catch {
    // Best effort - the toggle still works for the rest of this visit.
  }
}

/**
 * Provides the page's one <main> landmark - unless the page inside already
 * brought its own.
 *
 * A screen has to have exactly one: screen-reader users jump to it directly,
 * and two make that shortcut ambiguous. Pages written before this shell existed
 * (the analytics dashboard, for one) render their own <main>, and nesting ours
 * around it produced two. Rather than edit every such page, the frame checks
 * what it was handed and steps back to a plain <div> when a page owns the
 * landmark. Pages that do not (settings, library, study) get ours.
 *
 * Measured after render rather than guessed from the route, so a page that
 * starts or stops rendering its own is handled without anyone updating a list.
 */
function MainLandmark({ children }) {
  const ref = useRef(null);
  const [pageOwnsMain, setPageOwnsMain] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const check = () => setPageOwnsMain(Boolean(el.querySelector("main, [role='main']")));
    check();
    const observer = new MutationObserver(check);
    observer.observe(el, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  const Tag = pageOwnsMain ? "div" : "main";
  return (
    <Tag ref={ref} id="main" className="max-w-5xl mx-auto px-4 py-6 sm:px-6">
      {children}
    </Tag>
  );
}

export default function AppShell() {
  const navigate = useNavigate();
  const { currentUser, profile } = useAuth();
  // Manual, user-driven collapse - independent of the existing md: breakpoint
  // behavior (which already goes icon-only below md regardless). This lets a
  // learner reclaim sidebar width on a desktop-size screen too.
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      const next = !value;
      writeStoredCollapsed(next);
      return next;
    });
  };

  const handleSignOut = async () => {
    await signOut(auth);
    navigate("/signin", { replace: true });
  };

  const navItems = [
    ...NAV,
    ...(profile?.mode === "corporate" ? CORPORATE_NAV : []),
    ...(profile?.corporate_role === "hr_admin" ? HR_NAV : []),
  ];

  const asideWidthClass = collapsed ? "w-16" : "w-16 md:w-60";
  const labelClass = collapsed ? "sr-only" : "sr-only md:not-sr-only";
  const justifyClass = collapsed ? "justify-center" : "justify-center md:justify-start";

  return (
    <div className="min-h-screen bg-page text-ink flex">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:p-2 focus:bg-surface focus:border focus:border-accent focus:rounded-md focus:z-50"
      >
        Skip to content
      </a>

      <aside className={`${asideWidthClass} shrink-0 border-r border-line bg-surface flex flex-col sticky top-0 h-screen transition-[width] duration-150`}>
        <div className="flex items-center justify-between gap-1 px-3 md:px-4 py-4 border-b border-line">
          <Link to="/" className="flex items-center gap-2 font-semibold text-lg min-w-0">
            <GraduationCap size={22} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
            <span className={`${labelClass} truncate`}>Adaptly</span>
          </Link>
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={collapsed}
            className="shrink-0 p-1.5 rounded-md text-muted hover:bg-page hover:text-ink transition-colors duration-150"
          >
            {collapsed ? (
              <PanelLeftOpen size={18} strokeWidth={1.75} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={18} strokeWidth={1.75} aria-hidden="true" />
            )}
          </button>
        </div>

        <nav aria-label="Main" className="flex flex-col gap-1 p-2 flex-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={navClass}
              // Styling alone does not announce the current page.
              aria-current={undefined}
            >
              {({ isActive }) => (
                <span
                  aria-current={isActive ? "page" : undefined}
                  className={`flex items-center gap-3 ${justifyClass} w-full`}
                >
                  <item.icon size={18} strokeWidth={1.75} className="shrink-0" aria-hidden="true" />
                  <span className={`${labelClass} truncate`}>{item.label}</span>
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line p-2 flex flex-col gap-1">
          <Link
            to="/settings"
            className={`flex items-center gap-3 ${justifyClass} px-3 py-2.5 rounded-md text-sm font-medium text-ink hover:bg-page`}
          >
            <SettingsIcon size={18} strokeWidth={1.75} className="shrink-0" aria-hidden="true" />
            <span className={`${labelClass} truncate`}>Settings</span>
          </Link>

          <span className={`${collapsed ? "hidden" : "hidden md:block"} px-3 py-1 text-xs text-muted truncate`}>
            {profile?.display_name || profile?.name || currentUser?.email}
          </span>

          <Button
            variant="secondary"
            onClick={handleSignOut}
            className={justifyClass}
          >
            <LogOut size={14} strokeWidth={1.75} aria-hidden="true" />
            <span className={labelClass}>Sign out</span>
          </Button>
        </div>
      </aside>

      <div className="flex-1 min-w-0">
        <MainLandmark>
          <Outlet />
        </MainLandmark>
      </div>
    </div>
  );
}
