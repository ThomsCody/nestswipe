import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import { photoUrl } from "@/api/photos";
import type { Listing, Comment, PriceHistoryEntry } from "@/types";

interface FavoriteDetailData {
  id: number;
  listing: Listing;
  comments: Comment[];
  price_history: PriceHistoryEntry[];
  visit_date: string | null;
  location: string | null;
  seller_name: string | null;
  seller_phone: string | null;
  seller_is_agency: boolean | null;
  created_at: string;
}

function Lightbox({
  photos,
  index,
  onClose,
  onChangeIndex,
}: {
  photos: Listing["photos"];
  index: number;
  onClose: () => void;
  onChangeIndex: (i: number) => void;
}) {
  const touchStartX = useRef<number | null>(null);

  const goPrev = useCallback(() => {
    onChangeIndex((index - 1 + photos.length) % photos.length);
  }, [index, photos.length, onChangeIndex]);

  const goNext = useCallback(() => {
    onChangeIndex((index + 1) % photos.length);
  }, [index, photos.length, onChangeIndex]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "ArrowRight") goNext();
    };
    window.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  }, [onClose, goPrev, goNext]);

  const onTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0]!.clientX;
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null) return;
    const dx = e.changedTouches[0]!.clientX - touchStartX.current;
    if (Math.abs(dx) > 50) {
      dx < 0 ? goNext() : goPrev();
    }
    touchStartX.current = null;
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
      onClick={onClose}
    >
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 text-white/70 hover:text-white z-10"
      >
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Counter */}
      <span className="absolute top-4 left-4 text-white/70 text-sm">
        {index + 1} / {photos.length}
      </span>

      {/* Prev arrow */}
      {photos.length > 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); goPrev(); }}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-white/60 hover:text-white p-2"
        >
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      {/* Image */}
      <img
        src={photoUrl(photos[index]!.s3_key)}
        alt=""
        className="max-h-[90vh] max-w-[90vw] object-contain select-none"
        onClick={(e) => e.stopPropagation()}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
        draggable={false}
      />

      {/* Next arrow */}
      {photos.length > 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); goNext(); }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-white/60 hover:text-white p-2"
        >
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      )}
    </div>
  );
}

function Gallery({ photos }: { photos: Listing["photos"] }) {
  const [selected, setSelected] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  if (!photos.length) return null;

  return (
    <div>
      <div
        className="h-72 bg-gray-900 rounded-lg overflow-hidden mb-2 cursor-pointer"
        onClick={() => setLightboxOpen(true)}
      >
        <img
          src={photoUrl(photos[selected]!.s3_key)}
          alt=""
          className="w-full h-full object-contain"
        />
      </div>
      {photos.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-2">
          {photos.map((p, i) => (
            <button
              key={p.id}
              onClick={() => setSelected(i)}
              className={`flex-shrink-0 w-16 h-16 rounded overflow-hidden border-2 ${
                i === selected ? "border-indigo-500" : "border-transparent"
              }`}
            >
              <img
                src={photoUrl(p.s3_key)}
                alt=""
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      )}
      {lightboxOpen && (
        <Lightbox
          photos={photos}
          index={selected}
          onClose={() => setLightboxOpen(false)}
          onChangeIndex={setSelected}
        />
      )}
    </div>
  );
}

function PriceChart({ history }: { history: PriceHistoryEntry[] }) {
  if (history.length <= 1) return null;

  const prices = history.map((h) => h.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;

  return (
    <div className="mt-4">
      <h3 className="text-sm font-medium text-gray-700 mb-2">Price History</h3>
      <div className="bg-gray-50 rounded-lg p-3">
        <div className="flex items-end gap-1 h-24">
          {history.map((h, i) => {
            const height = ((h.price - min) / range) * 80 + 20;
            return (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <span className="text-[10px] text-gray-400">
                  {Math.round(h.price / 1000)}k
                </span>
                <div
                  className="w-full bg-indigo-400 rounded-t"
                  style={{ height: `${height}%` }}
                />
                <span className="text-[10px] text-gray-400">
                  {new Date(h.observed_at).toLocaleDateString("fr-FR", { month: "short", day: "numeric" })}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function FavoriteDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [comment, setComment] = useState("");

  const [visitDate, setVisitDate] = useState("");
  const [location, setLocation] = useState("");
  const [sellerName, setSellerName] = useState("");
  const [sellerPhone, setSellerPhone] = useState("");
  const [sellerIsAgency, setSellerIsAgency] = useState(false);

  const { data, isLoading } = useQuery<FavoriteDetailData>({
    queryKey: ["favorite", id],
    queryFn: () => client.get(`/favorites/${id}`).then((r) => r.data),
  });

  useEffect(() => {
    if (data) {
      setVisitDate(data.visit_date ? data.visit_date.slice(0, 16) : "");
      setLocation(data.location ?? "");
      setSellerName(data.seller_name ?? "");
      setSellerPhone(data.seller_phone ?? "");
      setSellerIsAgency(data.seller_is_agency ?? false);
    }
  }, [data]);

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      client.patch(`/favorites/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorite", id] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const isDirty =
    data != null &&
    (visitDate !== (data.visit_date ? data.visit_date.slice(0, 16) : "") ||
      location !== (data.location ?? "") ||
      sellerName !== (data.seller_name ?? "") ||
      sellerPhone !== (data.seller_phone ?? "") ||
      sellerIsAgency !== (data.seller_is_agency ?? false));

  const deleteMutation = useMutation({
    mutationFn: () => client.delete(`/favorites/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      navigate("/favorites");
    },
  });

  const commentMutation = useMutation({
    mutationFn: (body: string) => client.post(`/favorites/${id}/comments`, { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorite", id] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      setComment("");
    },
  });

  const deleteCommentMutation = useMutation({
    mutationFn: (commentId: number) => client.delete(`/favorites/${id}/comments/${commentId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorite", id] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  if (isLoading) return <p className="text-gray-500">Loading...</p>;
  if (!data) return <p className="text-red-500">Favorite not found.</p>;

  const { listing } = data;

  return (
    <div className="max-w-2xl mx-auto">
      <button
        onClick={() => navigate("/favorites")}
        className="text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        &larr; Back to favorites
      </button>

      <Gallery photos={listing.photos} />

      <div className="mt-4">
        <h2 className="text-xl font-semibold text-gray-900">{listing.title}</h2>
        <div className="flex flex-wrap gap-3 text-sm text-gray-600 mt-2">
          {listing.price != null && (
            <span className="font-medium text-gray-900">
              {listing.price.toLocaleString("fr-FR")} &euro;
            </span>
          )}
          {listing.sqm != null && <span>{listing.sqm} m&sup2;</span>}
          {listing.price_per_sqm != null && (
            <span>{listing.price_per_sqm.toLocaleString("fr-FR")} &euro;/m&sup2;</span>
          )}
          {listing.bedrooms != null && <span>{listing.bedrooms} ch.</span>}
        </div>
        {(listing.city || listing.district) && (
          <p className="text-sm text-gray-500 mt-1">
            {[listing.district, listing.city].filter(Boolean).join(", ")}
          </p>
        )}
        {listing.description && (
          <p className="text-sm text-gray-600 mt-3">{listing.description}</p>
        )}
        {/* Visit & Contact */}
        <div className="mt-4 p-4 bg-gray-50 rounded-lg">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Visit &amp; Contact</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Visit date</label>
              <input
                type="datetime-local"
                value={visitDate}
                onChange={(e) => setVisitDate(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Location / address</label>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="Full address for the visit"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Seller name</label>
              <input
                type="text"
                value={sellerName}
                onChange={(e) => setSellerName(e.target.value)}
                placeholder="Name"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Seller phone</label>
              <input
                type="tel"
                value={sellerPhone}
                onChange={(e) => setSellerPhone(e.target.value)}
                placeholder="Phone number"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
              />
            </div>
            <div className="sm:col-span-2 flex items-center gap-2">
              <input
                type="checkbox"
                id="seller-agency"
                checked={sellerIsAgency}
                onChange={(e) => setSellerIsAgency(e.target.checked)}
                className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="seller-agency" className="text-sm text-gray-600">
                This is an agency
              </label>
            </div>
          </div>
          <button
            disabled={!isDirty || updateMutation.isPending}
            onClick={() =>
              updateMutation.mutate({
                visit_date: visitDate || null,
                location: location || null,
                seller_name: sellerName || null,
                seller_phone: sellerPhone || null,
                seller_is_agency: sellerIsAgency,
              })
            }
            className="mt-3 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {updateMutation.isPending ? "Saving..." : "Save"}
          </button>
        </div>

        {listing.external_url && (
          <a
            href={listing.external_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block mt-3 text-sm text-indigo-600 hover:underline"
          >
            View original listing &rarr;
          </a>
        )}
      </div>

      <PriceChart history={data.price_history} />

      {/* Comments */}
      <div className="mt-6">
        <h3 className="text-sm font-medium text-gray-700 mb-3">
          Comments ({data.comments.length})
        </h3>
        <div className="space-y-3">
          {data.comments.map((c) => (
            <div key={c.id} className="bg-gray-50 rounded-lg p-3">
              <div className="flex justify-between items-start">
                <div>
                  <span className="text-sm font-medium text-gray-900">{c.user_name}</span>
                  <span className="text-xs text-gray-400 ml-2">
                    {new Date(c.created_at).toLocaleString("fr-FR")}
                  </span>
                </div>
                <button
                  onClick={() => deleteCommentMutation.mutate(c.id)}
                  className="text-xs text-red-400 hover:text-red-600"
                >
                  Delete
                </button>
              </div>
              <p className="text-sm text-gray-700 mt-1">{c.body}</p>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-3">
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add a comment..."
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && comment.trim()) {
                commentMutation.mutate(comment.trim());
              }
            }}
          />
          <button
            onClick={() => comment.trim() && commentMutation.mutate(comment.trim())}
            disabled={!comment.trim() || commentMutation.isPending}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>

      <div className="mt-6 pb-8 border-t pt-4">
        <button
          onClick={() => deleteMutation.mutate()}
          className="text-sm text-red-500 hover:text-red-700"
        >
          Remove from favorites
        </button>
      </div>
    </div>
  );
}
