import { useState, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import type { AxiosError } from "axios";

interface UserStatus {
  has_api_key: boolean;
  has_gmail_token: boolean;
}

interface ImportResponse {
  favorite_id: number;
  listing: { title: string };
  created: boolean;
  already_favorited: boolean;
}

export default function ImportUrlButton() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: userStatus } = useQuery<UserStatus>({
    queryKey: ["user-status"],
    queryFn: () => client.get("/auth/me").then((r) => r.data),
    staleTime: Infinity,
  });

  const mutation = useMutation<ImportResponse, AxiosError<{ detail: string }>, string>({
    mutationFn: (importUrl) =>
      client.post("/listings/import", { url: importUrl }).then((r) => r.data),
    onSuccess: (data) => {
      const suffix = data.already_favorited ? " (already in favorites)" : "";
      setMessage({ text: `Added: ${data.listing.title}${suffix}`, ok: true });
      setUrl("");
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      setTimeout(() => {
        setOpen(false);
        setMessage(null);
      }, 2000);
    },
    onError: (err) => {
      setMessage({
        text: err.response?.data?.detail || "Import failed. Please try again.",
        ok: false,
      });
    },
  });

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Hide entirely if no API key
  if (!userStatus?.has_api_key) return null;

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
        Import URL
      </button>
    );
  }

  return (
    <div className="inline-flex items-center gap-2">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (url.trim()) mutation.mutate(url.trim());
        }}
        className="inline-flex items-center gap-2"
      >
        <input
          ref={inputRef}
          type="url"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setMessage(null);
          }}
          placeholder="Paste listing URL..."
          disabled={mutation.isPending}
          className="w-72 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!url.trim() || mutation.isPending}
          className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg disabled:opacity-50 transition-colors"
        >
          {mutation.isPending ? (
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            "Import"
          )}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setUrl("");
            setMessage(null);
          }}
          disabled={mutation.isPending}
          className="px-2 py-1.5 text-sm text-gray-500 hover:text-gray-700 disabled:opacity-50"
        >
          Cancel
        </button>
      </form>
      {message && (
        <span className={`text-sm ${message.ok ? "text-green-600" : "text-red-600"}`}>
          {message.text}
        </span>
      )}
    </div>
  );
}
