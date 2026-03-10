import { useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { photoUrl } from "@/api/photos";
import type { Listing, Comment, PriceHistoryEntry } from "@/types";
import PriceTrend from "@/components/PriceTrend";

/* ------------------------------------------------------------------ */
/*  Lightbox                                                          */
/* ------------------------------------------------------------------ */

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
      <button
        onClick={onClose}
        className="absolute top-4 right-4 text-white/70 hover:text-white z-10"
      >
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      <span className="absolute top-4 left-4 text-white/70 text-sm">
        {index + 1} / {photos.length}
      </span>

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

      <img
        src={photoUrl(photos[index]!.s3_key)}
        alt=""
        className="max-h-[90vh] max-w-[90vw] object-contain select-none"
        onClick={(e) => e.stopPropagation()}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
        draggable={false}
      />

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

/* ------------------------------------------------------------------ */
/*  Gallery                                                           */
/* ------------------------------------------------------------------ */

function Gallery({ photos }: { photos: Listing["photos"] }) {
  const [selected, setSelected] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const touchStartX = useRef<number | null>(null);
  if (!photos.length) return null;

  const goPrev = () => setSelected((i) => (i - 1 + photos.length) % photos.length);
  const goNext = () => setSelected((i) => (i + 1) % photos.length);

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
    <div>
      <div
        className="relative h-72 bg-gray-900 rounded-lg overflow-hidden mb-2 cursor-pointer"
        onClick={() => setLightboxOpen(true)}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <img
          src={photoUrl(photos[selected]!.s3_key)}
          alt=""
          className="w-full h-full object-contain"
        />
        {photos.length > 1 && (
          <>
            <button
              onClick={(e) => { e.stopPropagation(); goPrev(); }}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/70"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); goNext(); }}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/70"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <span className="absolute bottom-2 left-1/2 -translate-x-1/2 text-white/70 text-xs bg-black/50 px-2 py-0.5 rounded-full">
              {selected + 1} / {photos.length}
            </span>
          </>
        )}
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

/* ------------------------------------------------------------------ */
/*  PriceChart                                                        */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/*  Contact form (only shown for favorites)                           */
/* ------------------------------------------------------------------ */

interface ContactFormProps {
  visitDate: string;
  location: string;
  sellerName: string;
  sellerPhone: string;
  sellerIsAgency: boolean;
  isDirty: boolean;
  isSaving: boolean;
  onVisitDateChange: (v: string) => void;
  onLocationChange: (v: string) => void;
  onSellerNameChange: (v: string) => void;
  onSellerPhoneChange: (v: string) => void;
  onSellerIsAgencyChange: (v: boolean) => void;
  onSave: () => void;
}

function ContactForm(props: ContactFormProps) {
  return (
    <div className="mt-4 p-4 bg-gray-50 rounded-lg">
      <h3 className="text-sm font-medium text-gray-700 mb-3">Visit &amp; Contact</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="block text-xs text-gray-500 mb-1">Visit date</label>
          <input
            type="datetime-local"
            value={props.visitDate}
            onChange={(e) => props.onVisitDateChange(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="block text-xs text-gray-500 mb-1">Location / address</label>
          <input
            type="text"
            value={props.location}
            onChange={(e) => props.onLocationChange(e.target.value)}
            placeholder="Full address for the visit"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Seller name</label>
          <input
            type="text"
            value={props.sellerName}
            onChange={(e) => props.onSellerNameChange(e.target.value)}
            placeholder="Name"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Seller phone</label>
          <input
            type="tel"
            value={props.sellerPhone}
            onChange={(e) => props.onSellerPhoneChange(e.target.value)}
            placeholder="Phone number"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
          />
        </div>
        <div className="sm:col-span-2 flex items-center gap-2">
          <input
            type="checkbox"
            id="seller-agency"
            checked={props.sellerIsAgency}
            onChange={(e) => props.onSellerIsAgencyChange(e.target.checked)}
            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          <label htmlFor="seller-agency" className="text-sm text-gray-600">
            This is an agency
          </label>
        </div>
      </div>
      <button
        disabled={!props.isDirty || props.isSaving}
        onClick={props.onSave}
        className="mt-3 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {props.isSaving ? "Saving..." : "Save"}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Highlighted comment body (renders @mentions with styling)          */
/* ------------------------------------------------------------------ */

function HighlightedBody({ body }: { body: string }) {
  const parts = body.split(/(@\w+)/g);
  return (
    <p className="text-sm text-gray-700 mt-1">
      {parts.map((part, i) =>
        /^@\w+$/.test(part) ? (
          <span key={i} className="text-indigo-600 font-medium">{part}</span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </p>
  );
}

/* ------------------------------------------------------------------ */
/*  Comments section (only shown for favorites)                       */
/* ------------------------------------------------------------------ */

export interface HouseholdMember {
  id: number;
  name: string;
}

interface CommentsSectionProps {
  comments: Comment[];
  onAdd: (body: string) => void;
  onDelete: (commentId: number) => void;
  isAdding: boolean;
  householdMembers?: HouseholdMember[];
  currentUserId?: number;
}

function CommentsSection({ comments, onAdd, onDelete, isAdding, householdMembers, currentUserId }: CommentsSectionProps) {
  const [comment, setComment] = useState("");
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIndex, setMentionIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const otherMembers = (householdMembers ?? []).filter((m) => m.id !== currentUserId);

  const filteredMembers = mentionQuery !== null
    ? otherMembers.filter((m) => {
        const firstName = m.name.split(" ")[0]!.toLowerCase();
        return firstName.startsWith(mentionQuery.toLowerCase());
      })
    : [];

  const submit = () => {
    if (comment.trim()) {
      onAdd(comment.trim());
      setComment("");
      setMentionQuery(null);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setComment(val);

    // Detect @mention in progress
    const cursorPos = e.target.selectionStart ?? val.length;
    const textBeforeCursor = val.slice(0, cursorPos);
    const match = textBeforeCursor.match(/@(\w*)$/);
    if (match) {
      setMentionQuery(match[1]!);
      setMentionIndex(0);
    } else {
      setMentionQuery(null);
    }
  };

  const insertMention = (member: HouseholdMember) => {
    const firstName = member.name.split(" ")[0]!;
    const cursorPos = inputRef.current?.selectionStart ?? comment.length;
    const textBeforeCursor = comment.slice(0, cursorPos);
    const textAfterCursor = comment.slice(cursorPos);
    const beforeAt = textBeforeCursor.replace(/@\w*$/, "");
    const newVal = `${beforeAt}@${firstName} ${textAfterCursor}`;
    setComment(newVal);
    setMentionQuery(null);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (mentionQuery !== null && filteredMembers.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex((i) => Math.min(i + 1, filteredMembers.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertMention(filteredMembers[mentionIndex]!);
        return;
      }
      if (e.key === "Escape") {
        setMentionQuery(null);
        return;
      }
    }
    if (e.key === "Enter" && comment.trim()) submit();
  };

  return (
    <div className="mt-6">
      <h3 className="text-sm font-medium text-gray-700 mb-3">
        Comments ({comments.length})
      </h3>
      <div className="space-y-3">
        {comments.map((c) => (
          <div key={c.id} className="bg-gray-50 rounded-lg p-3">
            <div className="flex justify-between items-start">
              <div>
                <span className="text-sm font-medium text-gray-900">{c.user_name}</span>
                <span className="text-xs text-gray-400 ml-2">
                  {new Date(c.created_at).toLocaleString("fr-FR")}
                </span>
              </div>
              {currentUserId === c.user_id && (
                <button
                  onClick={() => onDelete(c.id)}
                  className="text-xs text-red-400 hover:text-red-600"
                >
                  Delete
                </button>
              )}
            </div>
            <HighlightedBody body={c.body} />
          </div>
        ))}
      </div>
      <div className="relative flex gap-2 mt-3">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            value={comment}
            onChange={handleChange}
            placeholder="Add a comment... (use @ to mention)"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
            onKeyDown={handleKeyDown}
            onBlur={() => {
              // Delay to allow click on dropdown
              setTimeout(() => setMentionQuery(null), 150);
            }}
          />
          {mentionQuery !== null && filteredMembers.length > 0 && (
            <div className="absolute bottom-full mb-1 left-0 w-full bg-white rounded-md shadow-lg border border-gray-200 z-10 max-h-32 overflow-y-auto">
              {filteredMembers.map((m, i) => (
                <button
                  key={m.id}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => insertMention(m)}
                  className={`w-full text-left px-3 py-1.5 text-sm ${
                    i === mentionIndex ? "bg-indigo-50 text-indigo-700" : "text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  {m.name}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={submit}
          disabled={!comment.trim() || isAdding}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main shared detail view                                           */
/* ------------------------------------------------------------------ */

export interface ListingDetailViewProps {
  listing: Listing;
  priceHistory: PriceHistoryEntry[];
  backLabel: string;
  backTo: string;
  contactForm?: ReactNode;
  commentsSection?: ReactNode;
  bottomAction: ReactNode;
}

export { ContactForm, CommentsSection };

export default function ListingDetailView({
  listing,
  priceHistory,
  backLabel,
  backTo,
  contactForm,
  commentsSection,
  bottomAction,
}: ListingDetailViewProps) {
  const navigate = useNavigate();

  return (
    <div className="max-w-2xl mx-auto">
      <button
        onClick={() => navigate(backTo)}
        className="text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        &larr; {backLabel}
      </button>

      <Gallery photos={listing.photos} />

      <div className="mt-4">
        <h2 className="text-xl font-semibold text-gray-900">{listing.title}</h2>
        <div className="flex flex-wrap gap-3 text-sm text-gray-600 mt-2">
          {listing.price != null && (
            <span className="font-medium text-gray-900">
              {listing.price.toLocaleString("fr-FR")} &euro;
              <PriceTrend history={priceHistory} />
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
        {listing.last_seen_at && (
          <p className="text-xs text-gray-400 mt-1">
            Last updated: {new Date(listing.last_seen_at).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
          </p>
        )}
        {listing.description && (
          <p className="text-sm text-gray-600 mt-3">{listing.description}</p>
        )}

        {contactForm}

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

      <PriceChart history={priceHistory} />

      {commentsSection}

      <div className="mt-6 pb-8 border-t pt-4">
        {bottomAction}
      </div>
    </div>
  );
}
