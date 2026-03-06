import { useEffect, useRef, useState } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import client from "@/api/client";

const NAV_ITEMS = [
  { to: "/swipe", label: "Swipe" },
  { to: "/favorites", label: "Favorites" },
  { to: "/archives", label: "Archives" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  const { logout } = useAuth();
  const location = useLocation();
  const queryClient = useQueryClient();
  const prevRemaining = useRef<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  // Close mobile menu on navigation
  useEffect(() => {
    setMenuOpen(false);
  }, [location]);

  const { data: queueData } = useQuery<{ remaining: number }>({
    queryKey: ["queue-badge"],
    queryFn: () => client.get("/listings/queue?limit=1").then((r) => r.data),
    refetchInterval: 10_000,
  });

  // When the remaining count increases, new listings arrived — refresh the swipe queue
  useEffect(() => {
    if (queueData == null) return;
    if (prevRemaining.current !== null && queueData.remaining > prevRemaining.current) {
      queryClient.invalidateQueries({ queryKey: ["queue"] });
    }
    prevRemaining.current = queueData.remaining;
  }, [queueData, queryClient]);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/swipe" className="text-lg font-bold text-indigo-600">
            Nestswipe
          </Link>
          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-4">
            {NAV_ITEMS.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                className={`text-sm font-medium transition-colors ${
                  location.pathname.startsWith(to)
                    ? "text-indigo-600"
                    : "text-gray-500 hover:text-gray-900"
                }`}
              >
                {label}
                {to === "/swipe" && queueData && queueData.remaining > 0 && (
                  <span className="inline-flex items-center justify-center ml-1.5 px-1.5 py-0.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded-full">
                    {queueData.remaining}
                  </span>
                )}
              </Link>
            ))}
            <button
              onClick={logout}
              className="text-sm font-medium text-gray-500 hover:text-red-600 transition-colors"
            >
              Logout
            </button>
          </nav>

          {/* Mobile hamburger button */}
          <button
            className="md:hidden p-2 text-gray-500 hover:text-gray-900"
            onClick={() => setMenuOpen((o) => !o)}
            aria-label="Toggle menu"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {menuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile dropdown menu */}
        {menuOpen && (
          <nav className="md:hidden border-t border-gray-200 bg-white px-4 py-2 flex flex-col gap-1">
            {NAV_ITEMS.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                className={`block px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  location.pathname.startsWith(to)
                    ? "text-indigo-600 bg-indigo-50"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                {label}
                {to === "/swipe" && queueData && queueData.remaining > 0 && (
                  <span className="inline-flex items-center justify-center ml-1.5 px-1.5 py-0.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded-full">
                    {queueData.remaining}
                  </span>
                )}
              </Link>
            ))}
            <button
              onClick={logout}
              className="text-left px-3 py-2 rounded-md text-sm font-medium text-gray-600 hover:bg-red-50 hover:text-red-600 transition-colors"
            >
              Logout
            </button>
          </nav>
        )}
      </header>
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
