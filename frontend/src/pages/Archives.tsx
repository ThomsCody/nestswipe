import { useEffect, useRef, useCallback } from "react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import { photoUrl } from "@/api/photos";
import type { Listing } from "@/types";
import PriceTrend from "@/components/PriceTrend";

interface ArchiveItem {
  listing: Listing;
  passed_at: string;
}

interface ArchivesData {
  archives: ArchiveItem[];
  total: number;
}

const PER_PAGE = 8;

export default function Archives() {
  const queryClient = useQueryClient();
  const sentinelRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery<ArchivesData>({
      queryKey: ["archives"],
      queryFn: ({ pageParam }) =>
        client
          .get("/archives", { params: { page: pageParam, per_page: PER_PAGE } })
          .then((r) => r.data),
      initialPageParam: 1,
      getNextPageParam: (lastPage, allPages) => {
        const loaded = allPages.reduce((n, p) => n + p.archives.length, 0);
        return loaded < lastPage.total ? allPages.length + 1 : undefined;
      },
    });

  const handleIntersect = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    },
    [fetchNextPage, hasNextPage, isFetchingNextPage],
  );

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(handleIntersect, { rootMargin: "200px" });
    observer.observe(el);
    return () => observer.disconnect();
  }, [handleIntersect]);

  const restore = useMutation({
    mutationFn: (listingId: number) =>
      client.post(`/archives/${listingId}/restore`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archives"] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const allItems = data?.pages.flatMap((p) => p.archives) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  if (isLoading) return <p className="text-gray-500">Loading...</p>;

  if (!allItems.length) {
    return (
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Archives</h2>
        <p className="text-gray-500">No passed listings yet.</p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-semibold text-gray-900 mb-4">
        Archives ({total})
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {allItems.map((item) => (
          <div
            key={item.listing.id}
            className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
          >
            <div className="h-40 bg-gray-200">
              {item.listing.photos[0] && (
                <img
                  src={photoUrl(item.listing.photos[0].s3_key)}
                  alt=""
                  className="w-full h-full object-cover"
                />
              )}
            </div>
            <div className="p-3">
              <div className="flex flex-wrap gap-1 mb-1">
                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-100 text-indigo-700">
                  {item.listing.source}
                </span>
                {item.listing.floor != null && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-100 text-amber-700">
                    {item.listing.floor === 0 ? "RDC" : `${item.listing.floor}e ét.`}
                  </span>
                )}
                {item.listing.rooms != null && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-700">
                    {item.listing.rooms} p.
                  </span>
                )}
                {item.listing.bedrooms != null && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-teal-100 text-teal-700">
                    {item.listing.bedrooms} ch.
                  </span>
                )}
              </div>
              <h3 className="font-medium text-gray-900 text-sm truncate">
                {item.listing.title}
              </h3>
              <div className="flex gap-2 text-xs text-gray-500 mt-1">
                {item.listing.price != null && (
                  <span className="font-medium text-gray-700">
                    {item.listing.price.toLocaleString("fr-FR")} &euro;
                    <PriceTrend history={item.listing.price_history} />
                  </span>
                )}
                {item.listing.sqm != null && <span>{item.listing.sqm} m&sup2;</span>}
                {item.listing.rooms != null && (
                  <span>{item.listing.rooms} p.</span>
                )}
                {item.listing.bedrooms != null && (
                  <span>{item.listing.bedrooms} ch.</span>
                )}
              </div>
              <div className="flex items-center justify-between mt-2">
                {item.listing.city || item.listing.district ? (
                  <p className="text-xs text-gray-400">
                    {[item.listing.district, item.listing.city]
                      .filter(Boolean)
                      .join(", ")}
                  </p>
                ) : (
                  <span />
                )}
                <button
                  onClick={() => restore.mutate(item.listing.id)}
                  disabled={restore.isPending}
                  className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded bg-pink-50 text-pink-600 hover:bg-pink-100 transition-colors disabled:opacity-50"
                >
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
                  </svg>
                  Add to favorites
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
      <div ref={sentinelRef} className="h-10 flex items-center justify-center">
        {isFetchingNextPage && (
          <p className="text-sm text-gray-400">Loading more...</p>
        )}
      </div>
    </div>
  );
}
