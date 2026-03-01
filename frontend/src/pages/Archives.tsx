import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import { photoUrl } from "@/api/photos";
import type { Listing } from "@/types";

interface ArchiveItem {
  listing: Listing;
  passed_at: string;
}

interface ArchivesData {
  archives: ArchiveItem[];
  total: number;
}

export default function Archives() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<ArchivesData>({
    queryKey: ["archives"],
    queryFn: () => client.get("/archives").then((r) => r.data),
  });

  const restore = useMutation({
    mutationFn: (listingId: number) =>
      client.post(`/archives/${listingId}/restore`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archives"] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  if (isLoading) return <p className="text-gray-500">Loading...</p>;

  if (!data?.archives.length) {
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
        Archives ({data.total})
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {data.archives.map((item) => (
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
              </div>
              <h3 className="font-medium text-gray-900 text-sm truncate">
                {item.listing.title}
              </h3>
              <div className="flex gap-2 text-xs text-gray-500 mt-1">
                {item.listing.price != null && (
                  <span className="font-medium text-gray-700">
                    {item.listing.price.toLocaleString("fr-FR")} &euro;
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
                  className="text-xs font-medium px-2.5 py-1 rounded bg-indigo-50 text-indigo-600 hover:bg-indigo-100 transition-colors disabled:opacity-50"
                >
                  Restore
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
