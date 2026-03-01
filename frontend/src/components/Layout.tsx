import { Outlet, Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import client from "@/api/client";

const NAV_ITEMS = [
  { to: "/swipe", label: "Swipe" },
  { to: "/favorites", label: "Favorites" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  const { logout } = useAuth();
  const location = useLocation();

  const { data: queueData } = useQuery<{ remaining: number }>({
    queryKey: ["queue"],
    queryFn: () => client.get("/listings/queue?limit=1").then((r) => r.data),
    refetchInterval: 10_000,
  });

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/swipe" className="text-lg font-bold text-indigo-600">
            Nestswipe
          </Link>
          <nav className="flex items-center gap-4">
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
        </div>
      </header>
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
