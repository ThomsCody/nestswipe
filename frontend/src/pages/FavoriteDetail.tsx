import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import type { Listing, Comment, PriceHistoryEntry } from "@/types";
import ListingDetailView, { ContactForm, CommentsSection } from "@/components/ListingDetailView";
import type { HouseholdMember } from "@/components/ListingDetailView";
import ErrorBox from "@/components/ErrorBox";
import OfferSection from "@/components/OfferSection";

interface FavoriteOwner {
  id: number;
  name: string;
  picture: string | null;
}

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
  status: string;
  owner: FavoriteOwner | null;
  created_at: string;
  offer_price: string | null;
  renovation_budget: string | null;
}

interface HouseholdData {
  id: number;
  name: string;
  members: HouseholdMember[];
}

interface UserInfo {
  id: number;
  name: string;
}

export default function FavoriteDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [visitDate, setVisitDate] = useState("");
  const [location, setLocation] = useState("");
  const [sellerName, setSellerName] = useState("");
  const [sellerPhone, setSellerPhone] = useState("");
  const [sellerIsAgency, setSellerIsAgency] = useState(false);
  const [status, setStatus] = useState("");
  const [ownerId, setOwnerId] = useState("");

  const { data, isLoading, isError, refetch } = useQuery<FavoriteDetailData>({
    queryKey: ["favorite", id],
    queryFn: () => client.get(`/favorites/${id}`).then((r) => r.data),
  });

  const { data: household } = useQuery<HouseholdData>({
    queryKey: ["household"],
    queryFn: () => client.get("/household").then((r) => r.data),
    staleTime: 60_000,
  });

  const { data: userInfo } = useQuery<UserInfo>({
    queryKey: ["auth-me"],
    queryFn: () => client.get("/auth/me").then((r) => r.data),
    staleTime: Infinity,
  });

  const { data: statuses } = useQuery<{ id: string; label: string }[]>({
    queryKey: ["favorite-statuses"],
    queryFn: () => client.get("/favorites/statuses").then((r) => r.data),
    staleTime: Infinity,
  });

  useEffect(() => {
    if (data) {
      setVisitDate(data.visit_date ? data.visit_date.slice(0, 16) : "");
      setLocation(data.location ?? "");
      setSellerName(data.seller_name ?? data.listing.agent_name ?? data.listing.agency_name ?? "");
      setSellerPhone(data.seller_phone ?? data.listing.contact_phone ?? "");
      setSellerIsAgency(data.seller_is_agency ?? !!data.listing.agency_name);
      setStatus(data.status);
      setOwnerId(data.owner?.id != null ? String(data.owner.id) : "");
    }
  // Saving an offer must not overwrite unsaved contact/follow-up edits.
  }, [data?.id, data?.visit_date, data?.location, data?.seller_name, data?.seller_phone,
    data?.seller_is_agency, data?.listing.agent_name, data?.listing.agency_name,
    data?.listing.contact_phone, data?.status, data?.owner?.id]);

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      client.patch(`/favorites/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorite", id] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const savedSellerName =
    data?.seller_name ?? data?.listing.agent_name ?? data?.listing.agency_name ?? "";
  const savedSellerPhone = data?.seller_phone ?? data?.listing.contact_phone ?? "";
  const savedSellerIsAgency = data?.seller_is_agency ?? !!data?.listing.agency_name;

  const isDirty = data != null && (
    visitDate !== (data.visit_date ? data.visit_date.slice(0, 16) : "") ||
    location !== (data.location ?? "") ||
    sellerName !== savedSellerName ||
    sellerPhone !== savedSellerPhone ||
    sellerIsAgency !== savedSellerIsAgency ||
    status !== data.status ||
    ownerId !== (data.owner?.id != null ? String(data.owner.id) : "")
  );

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
      queryClient.invalidateQueries({ queryKey: ["notifications-count"] });
    },
  });

  const deleteCommentMutation = useMutation({
    mutationFn: (commentId: number) => client.delete(`/favorites/${id}/comments/${commentId}`),
    onSuccess: () => {
      refetch();
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  if (isLoading) return <p className="text-gray-500">Loading...</p>;
  if (isError) return <ErrorBox message="Could not load this favorite." onRetry={() => refetch()} />;
  if (!data) return <p className="text-red-500">Favorite not found.</p>;

  return (
    <ListingDetailView
      listing={data.listing}
      priceHistory={data.price_history}
      backLabel="Back to favorites"
      backTo="/favorites"
      managementPanel={
        <>
        <div className="p-5 sm:p-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-950">Favorite follow-up</h2>
            <p className="mt-1 text-sm leading-5 text-gray-500">
              Keep the next steps and contact details together.
            </p>
          </div>

          <div className="mt-5 space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-500">Status</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              >
                {statuses?.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-gray-500">Assigned to</label>
              <select
                value={ownerId}
                onChange={(e) => setOwnerId(e.target.value)}
                className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              >
                <option value="">Nobody</option>
                {household?.members.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
          </div>

          <ContactForm
            visitDate={visitDate}
            location={location}
            sellerName={sellerName}
            sellerPhone={sellerPhone}
            sellerIsAgency={sellerIsAgency}
            listing={data.listing}
            onVisitDateChange={setVisitDate}
            onLocationChange={setLocation}
            onSellerNameChange={setSellerName}
            onSellerPhoneChange={setSellerPhone}
            onSellerIsAgencyChange={setSellerIsAgency}
          />

          <button
            type="button"
            disabled={!isDirty || updateMutation.isPending}
            onClick={() =>
              updateMutation.mutate({
                status,
                owner_id: ownerId ? Number(ownerId) : null,
                visit_date: visitDate || null,
                location: location || null,
                seller_name: sellerName || null,
                seller_phone: sellerPhone || null,
                seller_is_agency: sellerIsAgency,
              })
            }
            className="mt-5 min-h-11 w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {updateMutation.isPending ? "Saving..." : "Save changes"}
          </button>
        </div>
        <OfferSection
          key={data.id}
          favoriteId={data.id}
          offerPrice={data.offer_price ?? null}
          renovationBudget={data.renovation_budget ?? null}
        />
        </>
      }
      commentsSection={
        <CommentsSection
          comments={data.comments}
          onAdd={(body) => commentMutation.mutate(body)}
          onDelete={(commentId) => deleteCommentMutation.mutate(commentId)}
          isAdding={commentMutation.isPending}
          householdMembers={household?.members}
          currentUserId={userInfo?.id}
        />
      }
      bottomAction={
        <button
          type="button"
          onClick={() => deleteMutation.mutate()}
          className="min-h-11 text-sm font-medium text-red-500 hover:text-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
        >
          Remove from favorites
        </button>
      }
    />
  );
}
