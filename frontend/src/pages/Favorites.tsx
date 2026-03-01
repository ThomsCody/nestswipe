import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import client from "@/api/client";
import { photoUrl } from "@/api/photos";
import type { Listing } from "@/types";

interface FavoriteItem {
  id: number;
  listing: Listing;
  comment_count: number;
  has_visit_date: boolean;
  created_at: string;
}

interface FavoritesData {
  favorites: FavoriteItem[];
  total: number;
}

export default function Favorites() {
  const { data, isLoading } = useQuery<FavoritesData>({
    queryKey: ["favorites"],
    queryFn: () => client.get("/favorites").then((r) => r.data),
  });

  if (isLoading) return <p className="text-gray-500">Loading...</p>;

  if (!data?.favorites.length) {
    return (
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Favorites</h2>
        <p className="text-gray-500">No favorites yet. Swipe right on listings you like!</p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-semibold text-gray-900 mb-4">
        Favorites ({data.total})
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {data.favorites.map((fav) => (
          <Link
            key={fav.id}
            to={`/favorites/${fav.id}`}
            className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
          >
            <div className="h-40 bg-gray-200">
              {fav.listing.photos[0] && (
                <img
                  src={photoUrl(fav.listing.photos[0].s3_key)}
                  alt=""
                  className="w-full h-full object-cover"
                />
              )}
            </div>
            <div className="p-3">
              <div className="flex flex-wrap gap-1 mb-1">
                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-100 text-indigo-700">
                  {fav.listing.source}
                </span>
                {fav.listing.floor != null && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-100 text-amber-700">
                    {fav.listing.floor === 0 ? "RDC" : `${fav.listing.floor}e ét.`}
                  </span>
                )}
                {fav.listing.rooms != null && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-700">
                    {fav.listing.rooms} p.
                  </span>
                )}
                {fav.listing.bedrooms != null && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-teal-100 text-teal-700">
                    {fav.listing.bedrooms} ch.
                  </span>
                )}
              </div>
              <h3 className="font-medium text-gray-900 text-sm truncate">{fav.listing.title}</h3>
              <div className="flex gap-2 text-xs text-gray-500 mt-1">
                {fav.listing.price != null && (
                  <span className="font-medium text-gray-700">
                    {fav.listing.price.toLocaleString("fr-FR")} &euro;
                  </span>
                )}
                {fav.listing.sqm != null && <span>{fav.listing.sqm} m&sup2;</span>}
                {fav.listing.rooms != null && (
                  <span>{fav.listing.rooms} p.</span>
                )}
                {fav.listing.bedrooms != null && <span>{fav.listing.bedrooms} ch.</span>}
              </div>
              <div className="flex items-center justify-between mt-1">
                {(fav.listing.city || fav.listing.district) ? (
                  <p className="text-xs text-gray-400">
                    {[fav.listing.district, fav.listing.city].filter(Boolean).join(", ")}
                  </p>
                ) : <span />}
                <span className="inline-flex items-center gap-1.5">
                  {fav.has_visit_date && (
                    <svg className="w-3.5 h-3.5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  )}
                  {fav.comment_count > 0 && (
                    <span className="inline-flex items-center gap-0.5 text-xs text-gray-400">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                      {fav.comment_count}
                    </span>
                  )}
                </span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
