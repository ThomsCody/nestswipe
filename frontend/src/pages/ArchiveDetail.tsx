import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import type { Listing, PriceHistoryEntry } from "@/types";
import ListingDetailView from "@/components/ListingDetailView";

interface ArchiveDetailData {
  listing: Listing;
  price_history: PriceHistoryEntry[];
  passed_at: string;
}

export default function ArchiveDetail() {
  const { listingId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<ArchiveDetailData>({
    queryKey: ["archive", listingId],
    queryFn: () => client.get(`/archives/${listingId}`).then((r) => r.data),
  });

  const restoreMutation = useMutation({
    mutationFn: () => client.post(`/archives/${listingId}/restore`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["archives"] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      navigate("/favorites");
    },
  });

  if (isLoading) return <p className="text-gray-500">Loading...</p>;
  if (!data) return <p className="text-red-500">Archived listing not found.</p>;

  return (
    <ListingDetailView
      listing={data.listing}
      priceHistory={data.price_history}
      backLabel="Back to archives"
      backTo="/archives"
      bottomAction={
        <button
          onClick={() => restoreMutation.mutate()}
          disabled={restoreMutation.isPending}
          className="inline-flex items-center gap-1.5 rounded-md bg-pink-600 px-4 py-2 text-sm font-medium text-white hover:bg-pink-700 disabled:opacity-50"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
          </svg>
          {restoreMutation.isPending ? "Moving..." : "Move to favorites"}
        </button>
      }
    />
  );
}
