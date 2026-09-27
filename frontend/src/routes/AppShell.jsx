/**
 * The frame around every signed-in screen: nav, identity, sign out.
 *
 * Kept separate from the router so a page never has to render its own header,
 * and separate from `App` so the shell can change without touching routing.
 *
 * Two things here are accessibility rather than decoration:
 *
 * - **A skip link.** The nav is the first thing in the tab order on every
 *   page; without a skip link a keyboard user tabs through it before reaching
 *   the content, on every navigation.
 * - **`aria-current="page"`.** The active tab is styled, and styling alone
 *   does not tell a screen-reader user which one they are on.
 */

import { useLayoutEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { signOut } from "firebase/auth";

import { auth } from "../auth/firebase";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../ui";

const NAV = [
  { to: "/library", label: "My documents" },
  { to: "/study", label: "Study session" },
  { to: "/analytics", label: "Analytics" },
];

function navClass({ isActive }) {
  return [
    "px-3 py-2 rounded-md text-sm font-medium",
    isActive ? "bg-accent text-on-accent" : "text-ink hover:bg-page",
  ].join(" ");
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
    <Tag ref={ref} id="main" className="max-w-5xl mx-auto px-4 py-6">
      {children}
    </Tag>
  );
}

export default function AppShell() {
  const navigate = useNavigate();
  const { currentUser, profile } = useAuth();

  const handleSignOut = async () => {
    await signOut(auth);
    navigate("/signin", { replace: true });
  };

  return (
    <div className="min-h-screen bg-page text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:p-2 focus:bg-surface focus:border focus:border-accent focus:rounded-md"
      >
        Skip to content
      </a>

      <header className="border-b border-line bg-surface">
        <div className="max-w-5xl mx-auto px-4 py-3 flex flex-wrap items-center gap-3">
          <Link to="/" className="font-semibold text-lg mr-2">
            Adaptly
          </Link>

          <nav aria-label="Main" className="flex gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={navClass}
                // Styling alone does not announce the current page.
                aria-current={undefined}
              >
                {({ isActive }) => (
                  <span aria-current={isActive ? "page" : undefined}>{item.label}</span>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2 text-sm">
            <Link to="/settings" className="text-accent hover:underline">
              Settings
            </Link>
            <span className="text-muted hidden sm:inline">
              {profile?.display_name || profile?.name || currentUser?.email}
            </span>
            <Button variant="secondary" onClick={handleSignOut}>
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <MainLandmark>
        <Outlet />
      </MainLandmark>
    </div>
  );
}
