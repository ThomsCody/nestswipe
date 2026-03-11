import { useState, useRef, useEffect } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Link } from "react-router-dom";
import { photoUrl } from "@/api/photos";
import type { Listing } from "@/types";
import PriceTrend from "@/components/PriceTrend";
import OwnerAvatar from "./OwnerAvatar";

export interface FavoriteOwner {
  id: number;
  name: string;
  picture?: string | null;
}

export interface HouseholdMember {
  id: number;
  name: string;
  picture?: string;
}

export interface FavoriteItem {
  id: number;
  listing: Listing;
  comment_count: number;
  has_visit_date: boolean;
  status: string;
  owner: FavoriteOwner | null;
  created_at: string;
}

interface KanbanCardProps {
  item: FavoriteItem;
  members?: HouseholdMember[];
  onOwnerChange?: (favoriteId: number, ownerId: number | null) => void;
}

export default function KanbanCard({ item, members, onOwnerChange }: KanbanCardProps) {
  const [showPicker, setShowPicker] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
    data: { status: item.status },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  useEffect(() => {
    if (!showPicker) return;
    function handleClick(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowPicker(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showPicker]);

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <div className="relative bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow">
        <Link
          to={`/favorites/${item.id}`}
          className="block"
          onClick={(e) => {
            if (isDragging) e.preventDefault();
          }}
        >
          <div className="h-28 bg-gray-200">
            {item.listing.photos[0] && (
              <img
                src={photoUrl(item.listing.photos[0].s3_key)}
                alt=""
                className="w-full h-full object-cover"
              />
            )}
          </div>
          <div className="p-2.5">
            <h3 className="font-medium text-gray-900 text-sm truncate">{item.listing.title}</h3>
            <div className="flex items-center gap-2 text-xs text-gray-500 mt-1">
              {item.listing.price != null && (
                <span className="font-semibold text-gray-700">
                  {item.listing.price.toLocaleString("fr-FR")}&nbsp;&euro;
                  <PriceTrend history={item.listing.price_history} />
                </span>
              )}
              {item.listing.sqm != null && <span>{item.listing.sqm}&nbsp;m&sup2;</span>}
            </div>
            <div className="flex flex-wrap gap-1 mt-1.5">
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-100 text-indigo-700">
                {item.listing.source}
              </span>
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
            <div className="flex items-center justify-between mt-1.5">
              <span className="inline-flex items-center gap-1.5">
                {item.has_visit_date && (
                  <svg className="w-3.5 h-3.5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                )}
                {item.comment_count > 0 && (
                  <span className="inline-flex items-center gap-0.5 text-xs text-gray-400">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    {item.comment_count}
                  </span>
                )}
              </span>
              {/* spacer so the avatar area doesn't overlap link */}
              <span className="w-7" />
            </div>
          </div>
        </Link>

        {/* Assign button — sits outside the Link to avoid navigation */}
        <div className="absolute bottom-2.5 right-2.5" ref={pickerRef}>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              if (members && onOwnerChange) setShowPicker((v) => !v);
            }}
            className="relative block"
            title={item.owner ? item.owner.name : "Assigner"}
          >
            {item.owner ? (
              <OwnerAvatar name={item.owner.name} picture={item.owner.picture} />
            ) : (
              <span className="w-6 h-6 rounded-full border-2 border-dashed border-gray-300 flex items-center justify-center text-gray-400 hover:border-gray-400 hover:text-gray-500 transition-colors">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </span>
            )}
          </button>

          {showPicker && members && onOwnerChange && (
            <div className="absolute bottom-8 right-0 z-50 bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[140px]">
              {item.owner && (
                <button
                  type="button"
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOwnerChange(item.id, null);
                    setShowPicker(false);
                  }}
                >
                  <span className="w-5 h-5 rounded-full bg-gray-100 flex items-center justify-center text-gray-400">
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </span>
                  Personne
                </button>
              )}
              {members.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-gray-50 ${
                    item.owner?.id === m.id ? "font-semibold text-indigo-600" : "text-gray-700"
                  }`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onOwnerChange(item.id, m.id);
                    setShowPicker(false);
                  }}
                >
                  <OwnerAvatar name={m.name} picture={m.picture} />
                  {m.name.split(" ")[0]}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
