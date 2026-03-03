import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import { photoUrl } from "@/api/photos";
import type { Listing } from "@/types";
import PriceTrend from "@/components/PriceTrend";

interface QueueData {
  listings: Listing[];
  remaining: number;
}

function PhotoCarousel({ photos }: { photos: Listing["photos"] }) {
  const [index, setIndex] = useState(0);

  if (photos.length === 0) {
    return (
      <div className="w-full h-72 bg-gray-200 flex items-center justify-center text-gray-400">
        No photos
      </div>
    );
  }

  return (
    <div className="relative w-full h-72 bg-gray-900 overflow-hidden">
      <img
        src={photoUrl(photos[index]!.s3_key)}
        alt=""
        className="w-full h-full object-contain"
      />
      {photos.length > 1 && (
        <>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIndex((i) => (i > 0 ? i - 1 : photos.length - 1));
            }}
            className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/70"
          >
            &lt;
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIndex((i) => (i < photos.length - 1 ? i + 1 : 0));
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/70"
          >
            &gt;
          </button>
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
            {photos.map((_, i) => (
              <span
                key={i}
                className={`block w-2 h-2 rounded-full ${i === index ? "bg-white" : "bg-white/40"}`}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ListingCard({
  listing,
  onSwipe,
  isPending,
}: {
  listing: Listing;
  onSwipe: (action: "like" | "pass") => void;
  isPending: boolean;
}) {
  return (
    <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden max-w-md w-full">
      <PhotoCarousel photos={listing.photos} />
      <div className="p-4">
        <div className="flex flex-wrap gap-1.5 mb-2">
          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
            {listing.source}
          </span>
          {listing.floor != null && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
              {listing.floor === 0 ? "RDC" : `${listing.floor}e ét.`}
            </span>
          )}
          {listing.rooms != null && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
              {listing.rooms} p.
            </span>
          )}
          {listing.bedrooms != null && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-teal-100 text-teal-700">
              {listing.bedrooms} ch.
            </span>
          )}
        </div>
        <h3 className="font-semibold text-lg text-gray-900 mb-1">{listing.title}</h3>
        <div className="flex flex-wrap gap-3 text-sm text-gray-600 mb-2">
          {listing.price != null && (
            <span className="font-medium text-gray-900">
              {listing.price.toLocaleString("fr-FR")} &euro;
              <PriceTrend history={listing.price_history} />
            </span>
          )}
          {listing.sqm != null && <span>{listing.sqm} m&sup2;</span>}
          {listing.price_per_sqm != null && (
            <span>{listing.price_per_sqm.toLocaleString("fr-FR")} &euro;/m&sup2;</span>
          )}
          {listing.rooms != null && <span>{listing.rooms} p.</span>}
          {listing.bedrooms != null && <span>{listing.bedrooms} ch.</span>}
        </div>
        {(listing.city || listing.district) && (
          <p className="text-sm text-gray-500 mb-1">
            {[listing.district, listing.city].filter(Boolean).join(", ")}
          </p>
        )}
        {listing.location_detail && (
          <p className="text-xs text-gray-400 mb-2">{listing.location_detail}</p>
        )}
        {listing.external_url && (
          <a
            href={listing.external_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-indigo-600 hover:underline"
          >
            View original listing &rarr;
          </a>
        )}
      </div>
      <div className="flex border-t border-gray-200">
        <button
          onClick={() => onSwipe("pass")}
          disabled={isPending}
          className="flex-1 py-3 text-sm font-medium text-gray-500 hover:bg-red-50 hover:text-red-600 transition-colors disabled:opacity-50"
        >
          Pass
        </button>
        <div className="w-px bg-gray-200" />
        <button
          onClick={() => onSwipe("like")}
          disabled={isPending}
          className="flex-1 py-3 text-sm font-medium text-gray-500 hover:bg-green-50 hover:text-green-600 transition-colors disabled:opacity-50"
        >
          Like
        </button>
      </div>
    </div>
  );
}

export default function Swipe() {
  const queryClient = useQueryClient();

  const { data, isLoading, isFetching } = useQuery<QueueData>({
    queryKey: ["queue"],
    queryFn: () => client.get("/listings/queue?limit=10").then((r) => r.data),
  });

  const swipeMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      client.post(`/listings/${id}/swipe`, { action }),
    onMutate: async ({ id }) => {
      // Cancel in-flight refetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: ["queue"] });
      // Immediately remove the swiped listing from the cache
      queryClient.setQueryData<QueueData>(["queue"], (old) => {
        if (!old) return old;
        const filtered = old.listings.filter((l) => l.id !== id);
        return { listings: filtered, remaining: Math.max(0, old.remaining - 1) };
      });
    },
    onError: () => {
      // On any error (including 409 already-swiped), just refetch fresh data
      queryClient.invalidateQueries({ queryKey: ["queue"] });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queue-badge"] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      // Replenish the local queue when it runs low
      const current = queryClient.getQueryData<QueueData>(["queue"]);
      if (current && current.listings.length <= 2) {
        queryClient.invalidateQueries({ queryKey: ["queue"] });
      }
    },
  });

  const listings = data?.listings ?? [];
  const currentListing = listings[0];

  const handleSwipe = useCallback(
    (action: "like" | "pass") => {
      if (!currentListing || swipeMutation.isPending) return;
      swipeMutation.mutate({ id: currentListing.id, action });
    },
    [currentListing, swipeMutation],
  );

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") handleSwipe("pass");
      if (e.key === "ArrowRight") handleSwipe("like");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleSwipe]);

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (!currentListing) {
    // Still fetching → show spinner, not "all caught up"
    if (isFetching) {
      return (
        <div className="flex justify-center py-12">
          <p className="text-gray-500">Loading...</p>
        </div>
      );
    }
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">All caught up!</h2>
        <p className="text-gray-500">
          No new listings to review. Configure your API key in Settings and wait for the next email poll.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center py-4">
      <p className="text-sm text-gray-400 mb-4">
        {data?.remaining ?? 0} listing{(data?.remaining ?? 0) !== 1 ? "s" : ""} remaining
        <span className="ml-3 text-xs">(← pass | like →)</span>
      </p>
      <ListingCard
        key={currentListing.id}
        listing={currentListing}
        onSwipe={handleSwipe}
        isPending={swipeMutation.isPending}
      />
    </div>
  );
}
