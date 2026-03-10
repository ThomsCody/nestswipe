import { useEffect, useRef, useState } from "react";
import { Outlet, Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import client from "@/api/client";
import type { Notification } from "@/types";

const NAV_ITEMS = [
  { to: "/swipe", label: "Swipe" },
  { to: "/favorites", label: "Favorites" },
  { to: "/archives", label: "Archives" },
  { to: "/settings", label: "Settings" },
];

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function NotificationBell() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { data: countData } = useQuery<{ unread: number }>({
    queryKey: ["notifications-count"],
    queryFn: () => client.get("/notifications/count").then((r) => r.data),
    refetchInterval: 10_000,
  });

  const { data: notifications, refetch } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: () => client.get("/notifications").then((r) => r.data),
    enabled: open,
  });

  const markReadMutation = useMutation({
    mutationFn: (id: number) => client.post(`/notifications/${id}/read`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications-count"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => client.post("/notifications/read-all"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications-count"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  // Close dropdown on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Refetch notifications when opening
  useEffect(() => {
    if (open) refetch();
  }, [open, refetch]);

  const unread = countData?.unread ?? 0;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative p-1.5 text-gray-500 hover:text-gray-900 transition-colors"
        aria-label="Notifications"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold bg-red-500 text-white rounded-full">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-50 max-h-96 overflow-y-auto">
          <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
            <span className="text-sm font-medium text-gray-700">Notifications</span>
            {unread > 0 && (
              <button
                onClick={() => markAllReadMutation.mutate()}
                className="text-xs text-indigo-600 hover:text-indigo-800"
              >
                Mark all as read
              </button>
            )}
          </div>
          {!notifications || notifications.length === 0 ? (
            <p className="px-4 py-6 text-sm text-gray-400 text-center">No new notifications</p>
          ) : (
            notifications.map((n) => (
              <button
                key={n.id}
                onClick={() => {
                  markReadMutation.mutate(n.id);
                  setOpen(false);
                  queryClient.invalidateQueries({ queryKey: ["favorite", String(n.favorite_id)] });
                  navigate(`/favorites/${n.favorite_id}`);
                }}
                className="w-full text-left px-4 py-3 hover:bg-gray-50 border-b border-gray-50 last:border-0 transition-colors"
              >
                <p className="text-sm text-gray-900">
                  <span className="font-medium">{n.commenter_name}</span>
                  {" mentioned you on "}
                  <span className="font-medium">{n.listing_title}</span>
                </p>
                <p className="text-xs text-gray-500 mt-0.5 truncate">{n.comment_body}</p>
                <p className="text-xs text-gray-400 mt-0.5">{timeAgo(n.created_at)}</p>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

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
            <NotificationBell />
            <button
              onClick={logout}
              className="text-sm font-medium text-gray-500 hover:text-red-600 transition-colors"
            >
              Logout
            </button>
          </nav>

          {/* Mobile: bell + hamburger */}
          <div className="flex md:hidden items-center gap-2">
            <NotificationBell />
            <button
              className="p-2 text-gray-500 hover:text-gray-900"
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
