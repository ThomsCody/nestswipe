import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";

interface SettingsData {
  openai_api_key_set: boolean;
  openai_api_key_masked: string | null;
  gmail_connected: boolean;
}

interface HouseholdMember {
  id: number;
  name: string;
  email: string;
  picture: string | null;
}

interface HouseholdData {
  id: number;
  name: string;
  members: HouseholdMember[];
}

interface InviteData {
  id: number;
  inviter_name: string;
  household_name: string;
  status: string;
}

interface SentInviteData {
  id: number;
  invitee_email: string;
  status: string;
  created_at: string;
}

export default function Settings() {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");

  const { data: settings, isLoading } = useQuery<SettingsData>({
    queryKey: ["settings"],
    queryFn: () => client.get("/settings").then((r) => r.data),
  });

  const { data: household } = useQuery<HouseholdData>({
    queryKey: ["household"],
    queryFn: () => client.get("/household").then((r) => r.data),
  });

  const { data: invites } = useQuery<InviteData[]>({
    queryKey: ["invites"],
    queryFn: () => client.get("/household/invites").then((r) => r.data),
  });

  const apiKeyMutation = useMutation({
    mutationFn: (key: string) => client.put("/settings", { openai_api_key: key }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setApiKey("");
    },
  });

  const { data: sentInvites } = useQuery<SentInviteData[]>({
    queryKey: ["sentInvites"],
    queryFn: () => client.get("/household/invites/sent").then((r) => r.data),
  });

  const inviteMutation = useMutation({
    mutationFn: (email: string) => client.post("/household/invite", { email }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sentInvites"] });
      setInviteEmail("");
    },
  });

  const acceptMutation = useMutation({
    mutationFn: (id: number) => client.post(`/household/invites/${id}/accept`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["household"] });
      queryClient.invalidateQueries({ queryKey: ["invites"] });
    },
  });

  const declineMutation = useMutation({
    mutationFn: (id: number) => client.post(`/household/invites/${id}/decline`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invites"] }),
  });

  if (isLoading) return <p className="text-gray-500">Loading...</p>;

  return (
    <div className="max-w-lg space-y-6">
      <h2 className="text-xl font-semibold text-gray-900">Settings</h2>

      {/* Pending invites */}
      {invites && invites.length > 0 && (
        <section className="bg-yellow-50 rounded-lg border border-yellow-200 p-4">
          <h3 className="text-sm font-medium text-yellow-800 mb-2">Pending Invitations</h3>
          {invites.map((inv) => (
            <div key={inv.id} className="flex items-center justify-between py-2">
              <p className="text-sm text-yellow-700">
                <strong>{inv.inviter_name}</strong> invited you to join{" "}
                <strong>{inv.household_name}</strong>
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => acceptMutation.mutate(inv.id)}
                  className="text-xs bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700"
                >
                  Accept
                </button>
                <button
                  onClick={() => declineMutation.mutate(inv.id)}
                  className="text-xs bg-gray-300 text-gray-700 px-3 py-1 rounded hover:bg-gray-400"
                >
                  Decline
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Gmail */}
      <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="text-sm font-medium text-gray-700 mb-1">Gmail Connection</h3>
        {settings?.gmail_connected ? (
          <p className="text-sm text-green-600">Connected</p>
        ) : (
          <p className="text-sm text-red-500">
            Not connected. Sign out and sign in again to grant Gmail access.
          </p>
        )}
      </section>

      {/* API Key */}
      <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="text-sm font-medium text-gray-700 mb-1">OpenAI API Key</h3>
        {settings?.openai_api_key_set && (
          <p className="text-xs text-gray-400 mb-3">
            Current: {settings.openai_api_key_masked}
          </p>
        )}
        <div className="flex gap-2">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
          />
          <button
            onClick={() => apiKeyMutation.mutate(apiKey)}
            disabled={!apiKey || apiKeyMutation.isPending}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {apiKeyMutation.isPending ? "Saving..." : "Save"}
          </button>
        </div>
        {settings?.openai_api_key_set && (
          <button
            onClick={() => apiKeyMutation.mutate("")}
            className="mt-2 text-xs text-red-500 hover:text-red-700"
          >
            Remove API key
          </button>
        )}
      </section>

      {/* Household */}
      <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="text-sm font-medium text-gray-700 mb-3">Household</h3>
        {household && (
          <>
            <p className="text-sm text-gray-600 mb-2">{household.name}</p>
            <div className="space-y-2 mb-4">
              {household.members.map((m) => (
                <div key={m.id} className="flex items-center gap-2">
                  {m.picture && (
                    <img src={m.picture} alt="" className="w-6 h-6 rounded-full" />
                  )}
                  <span className="text-sm text-gray-700">{m.name}</span>
                  <span className="text-xs text-gray-400">{m.email}</span>
                </div>
              ))}
            </div>
            <h4 className="text-xs font-medium text-gray-500 mb-2">Invite someone</h4>
            <div className="flex gap-2">
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="partner@gmail.com"
                className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
              />
              <button
                onClick={() => inviteEmail.trim() && inviteMutation.mutate(inviteEmail.trim())}
                disabled={!inviteEmail.trim() || inviteMutation.isPending}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                Invite
              </button>
            </div>
            {inviteMutation.isSuccess && (
              <p className="text-xs text-green-600 mt-1">Invitation sent!</p>
            )}
            {inviteMutation.isError && (
              <p className="text-xs text-red-500 mt-1">Failed to send invite.</p>
            )}
            {sentInvites && sentInvites.length > 0 && (
              <div className="mt-4 border-t border-gray-100 pt-3">
                <h4 className="text-xs font-medium text-gray-500 mb-2">Sent invitations</h4>
                <div className="space-y-1.5">
                  {sentInvites.map((inv) => (
                    <div key={inv.id} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">{inv.invitee_email}</span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          inv.status === "pending"
                            ? "bg-yellow-100 text-yellow-700"
                            : inv.status === "accepted"
                              ? "bg-green-100 text-green-700"
                              : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {inv.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
