import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import KanbanBoard from "@/components/board/KanbanBoard";
import OwnerFilter from "@/components/board/OwnerFilter";
import ErrorBox from "@/components/ErrorBox";
import ImportUrlButton from "@/components/ImportUrlButton";
import type { FavoriteItem } from "@/components/board/KanbanCard";

interface FavoritesData {
  favorites: FavoriteItem[];
  total: number;
}

interface HouseholdMember {
  id: number;
  name: string;
  picture?: string;
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

export default function Favorites() {
  const queryClient = useQueryClient();
  const [ownerFilter, setOwnerFilter] = useState<number | null>(null);

  const { data, isLoading, isError, refetch } = useQuery<FavoritesData>({
    queryKey: ["favorites", ownerFilter],
    queryFn: () => {
      const params: Record<string, string> = { per_page: "200" };
      if (ownerFilter !== null) params.owner_id = String(ownerFilter);
      return client.get("/favorites", { params }).then((r) => r.data);
    },
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

  const archiveMutation = useMutation({
    mutationFn: (id: number) => client.delete(`/favorites/${id}`),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ["favorites", ownerFilter] });
      const prev = queryClient.getQueryData<FavoritesData>(["favorites", ownerFilter]);
      queryClient.setQueryData<FavoritesData>(["favorites", ownerFilter], (old) => {
        if (!old) return old;
        const favorites = old.favorites.filter((f) => f.id !== id);
        return { ...old, favorites, total: old.total - 1 };
      });
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(["favorites", ownerFilter], ctx.prev);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const ownerMutation = useMutation({
    mutationFn: ({ id, owner_id }: { id: number; owner_id: number | null }) =>
      client.patch(`/favorites/${id}`, { owner_id }).then((r) => r.data),
    onMutate: async ({ id, owner_id }) => {
      await queryClient.cancelQueries({ queryKey: ["favorites", ownerFilter] });
      const prev = queryClient.getQueryData<FavoritesData>(["favorites", ownerFilter]);
      queryClient.setQueryData<FavoritesData>(["favorites", ownerFilter], (old) => {
        if (!old) return old;
        return {
          ...old,
          favorites: old.favorites.map((f) => {
            if (f.id !== id) return f;
            const member = household?.members.find((m) => m.id === owner_id);
            return {
              ...f,
              owner: member ? { id: member.id, name: member.name, picture: member.picture ?? null } : null,
            };
          }),
        };
      });
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(["favorites", ownerFilter], ctx.prev);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      client.patch(`/favorites/${id}`, { status }),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ["favorites", ownerFilter] });
      const prev = queryClient.getQueryData<FavoritesData>(["favorites", ownerFilter]);
      queryClient.setQueryData<FavoritesData>(["favorites", ownerFilter], (old) => {
        if (!old) return old;
        return {
          ...old,
          favorites: old.favorites.map((f) => (f.id === id ? { ...f, status } : f)),
        };
      });
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(["favorites", ownerFilter], ctx.prev);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  if (isLoading) return <p className="text-gray-500">Loading...</p>;
  if (isError) return <ErrorBox message="Could not load favorites." onRetry={() => refetch()} />;

  if (!data?.favorites.length && ownerFilter === null) {
    return (
      <div>
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Favorites</h2>
          <ImportUrlButton />
        </div>
        <p className="text-gray-500">No favorites yet. Swipe right on listings you like!</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-xl font-semibold text-gray-900">
          Favorites ({data?.total ?? 0})
        </h2>
        <ImportUrlButton />
      </div>
      {household && (
        <div className="mb-4">
          <OwnerFilter
            members={household.members}
            currentUserId={userInfo?.id}
            value={ownerFilter}
            onChange={setOwnerFilter}
          />
        </div>
      )}
      <KanbanBoard
        items={data?.favorites ?? []}
        members={household?.members}
        onStatusChange={(id, status) => statusMutation.mutate({ id, status })}
        onArchive={(id) => archiveMutation.mutate(id)}
        onOwnerChange={(id, owner_id) => ownerMutation.mutate({ id, owner_id })}
      />
    </div>
  );
}
