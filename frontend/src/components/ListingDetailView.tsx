import { useState, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import type { Listing, Comment, PriceHistoryEntry } from "@/types";
import Gallery from "@/components/Gallery";
import PriceTrend from "@/components/PriceTrend";

/* ------------------------------------------------------------------ */
/*  Contact form (only shown for favorites)                           */
/* ------------------------------------------------------------------ */

interface ContactFormProps {
  visitDate: string;
  location: string;
  sellerName: string;
  sellerPhone: string;
  sellerIsAgency: boolean;
  listing?: Listing;
  onVisitDateChange: (v: string) => void;
  onLocationChange: (v: string) => void;
  onSellerNameChange: (v: string) => void;
  onSellerPhoneChange: (v: string) => void;
  onSellerIsAgencyChange: (v: boolean) => void;
}

function ContactForm(props: ContactFormProps) {
  const [isEditingOnMobile, setIsEditingOnMobile] = useState(false);

  const visitSummary = props.visitDate
    ? new Date(props.visitDate).toLocaleString("fr-FR", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "No visit scheduled";

  const contactSummary = [props.sellerName, props.sellerPhone].filter(Boolean).join(" · ");

  return (
    <div className="mt-6 border-t border-gray-200 pt-5">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-base font-semibold text-gray-900">Visit &amp; contact</h3>
        <button
          type="button"
          onClick={() => setIsEditingOnMobile((open) => !open)}
          className="min-h-11 rounded-md px-2 text-sm font-medium text-indigo-600 hover:text-indigo-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 lg:hidden"
          aria-expanded={isEditingOnMobile}
        >
          {isEditingOnMobile ? "Close" : "Edit"}
        </button>
      </div>

      {!isEditingOnMobile && (
        <dl className="mt-4 space-y-4 text-sm lg:hidden">
          <div>
            <dt className="text-xs font-medium text-gray-500">Visit</dt>
            <dd className="mt-1 font-medium text-gray-900">{visitSummary}</dd>
            {props.location && <dd className="mt-0.5 text-gray-600">{props.location}</dd>}
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-500">Contact</dt>
            <dd className="mt-1 text-gray-700">{contactSummary || "No contact details"}</dd>
            {props.sellerIsAgency && <dd className="mt-0.5 text-gray-500">Agency</dd>}
          </div>
        </dl>
      )}

      <div className={`${isEditingOnMobile ? "block" : "hidden"} mt-5 space-y-5 lg:block`}>
        <div className="space-y-4">
          <h4 className="text-sm font-medium text-gray-700">Visit</h4>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-gray-500">Visit date</label>
            <input
              type="datetime-local"
              value={props.visitDate}
              onChange={(e) => props.onVisitDateChange(e.target.value)}
              className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-gray-500">Location / address</label>
            <input
              type="text"
              value={props.location}
              onChange={(e) => props.onLocationChange(e.target.value)}
              placeholder="Full address for the visit"
              className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />
          </div>
        </div>

        <div className="space-y-4 border-t border-gray-200 pt-5">
          <h4 className="text-sm font-medium text-gray-700">Contact</h4>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-gray-500">Seller name</label>
            <input
              type="text"
              value={props.sellerName}
              onChange={(e) => props.onSellerNameChange(e.target.value)}
              placeholder={props.listing?.agent_name ?? props.listing?.agency_name ?? "Name"}
              className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-gray-500">Seller phone</label>
            <input
              type="tel"
              value={props.sellerPhone}
              onChange={(e) => props.onSellerPhoneChange(e.target.value)}
              placeholder={props.listing?.contact_phone ?? "Phone number"}
              className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
            />
          </div>
          <div className="flex min-h-11 items-center gap-3">
            <input
              type="checkbox"
              id="seller-agency"
              checked={props.sellerIsAgency}
              onChange={(e) => props.onSellerIsAgencyChange(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <label htmlFor="seller-agency" className="text-sm text-gray-600">
              This is an agency
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Highlighted comment body (renders @mentions with styling)          */
/* ------------------------------------------------------------------ */

function HighlightedBody({ body }: { body: string }) {
  const parts = body.split(/((?<=^|\s)@\w+)/g);
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
    <section>
      <h2 className="mb-4 text-lg font-semibold text-gray-900">
        Comments ({comments.length})
      </h2>
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
      <div className="relative mt-3 flex flex-col gap-2 sm:flex-row">
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
          className="min-h-11 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </section>
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
  createdAt?: string;
  managementPanel?: ReactNode;
  commentsSection?: ReactNode;
  bottomAction: ReactNode;
}

export { ContactForm, CommentsSection };

export default function ListingDetailView({
  listing,
  priceHistory,
  backLabel,
  backTo,
  createdAt,
  managementPanel,
  commentsSection,
  bottomAction,
}: ListingDetailViewProps) {
  const navigate = useNavigate();

  return (
    <div className="mx-auto max-w-6xl">
      <button
        onClick={() => navigate(backTo)}
        className="mb-5 min-h-11 text-sm font-medium text-gray-500 hover:text-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
      >
        &larr; {backLabel}
      </button>

      <div className="-mx-4 sm:mx-0">
        <Gallery
          photos={listing.photos}
          heightClass="h-64 sm:h-96 lg:h-[30rem]"
          hideThumbnailsOnMobile
        />
      </div>

      <div
        className={`mt-7 grid items-start gap-x-8 gap-y-8 ${
          managementPanel ? "lg:grid-cols-[minmax(0,1fr)_22rem]" : "lg:grid-cols-[minmax(0,48rem)]"
        }`}
      >
        <div className="min-w-0">
          <header className="border-b border-gray-200 pb-7">
            <h1 className="text-2xl font-semibold tracking-tight text-gray-950 sm:text-3xl">
              {listing.title}
            </h1>
            <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-2 text-sm text-gray-600">
              {listing.price != null && (
                <span className="text-xl font-semibold text-gray-950">
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
              <p className="mt-2 text-sm text-gray-600">
                {[listing.district, listing.city].filter(Boolean).join(", ")}
              </p>
            )}
            {createdAt && (
              <p className="mt-1 text-xs text-gray-400">
                Created: {new Date(createdAt).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
              </p>
            )}
            {listing.last_seen_at && (
              <p className="mt-1 text-xs text-gray-400">
                Last updated: {new Date(listing.last_seen_at).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
              </p>
            )}
          </header>

          <main className="mt-8 min-w-0 space-y-8">
            {listing.description && (
              <section>
                <h2 className="text-lg font-semibold text-gray-900">Description</h2>
                <p className="mt-4 max-w-3xl text-[15px] leading-7 text-gray-600">
                  {listing.description}
                </p>
              </section>
            )}

            {listing.external_url && (
              <a
                href={listing.external_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center text-sm font-medium text-indigo-600 hover:text-indigo-800 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              >
                View original listing &rarr;
              </a>
            )}

            {commentsSection}

            {!managementPanel && (
              <div className="border-t border-gray-200 pb-8 pt-6">
                {bottomAction}
              </div>
            )}
          </main>
        </div>

        {managementPanel && (
          <aside className="lg:sticky lg:top-20">
            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              {managementPanel}
              <div className="border-t border-gray-100 px-5 py-4 sm:px-6">
                {bottomAction}
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
