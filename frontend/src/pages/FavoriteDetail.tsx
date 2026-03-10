import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import type { Listing, Comment, PriceHistoryEntry } from "@/types";
import ListingDetailView, { ContactForm, CommentsSection } from "@/components/ListingDetailView";
import type { HouseholdMember } from "@/components/ListingDetailView";
import ErrorBox from "@/components/ErrorBox";

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
      contactForm={
        <ContactForm
          visitDate={visitDate}
          location={location}
          sellerName={sellerName}
          sellerPhone={sellerPhone}
          sellerIsAgency={sellerIsAgency}
          isDirty={isDirty}
          isSaving={updateMutation.isPending}
          onVisitDateChange={setVisitDate}
          onLocationChange={setLocation}
          onSellerNameChange={setSellerName}
          onSellerPhoneChange={setSellerPhone}
          onSellerIsAgencyChange={setSellerIsAgency}
          onSave={() =>
            updateMutation.mutate({
              visit_date: visitDate || null,
              location: location || null,
              seller_name: sellerName || null,
              seller_phone: sellerPhone || null,
              seller_is_agency: sellerIsAgency,
            })
          }
        />
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
          onClick={() => deleteMutation.mutate()}
          className="text-sm text-red-500 hover:text-red-700"
        >
          Remove from favorites
        </button>
      }
    />
  );
}
