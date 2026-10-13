import { screen } from "@testing-library/react";
import { vi } from "vitest";
import Swipe from "./Swipe";
import Archives from "./Archives";
import KanbanCard from "@/components/board/KanbanCard";
import { renderWithProviders } from "@/test/utils";

const mockGet = vi.fn();
vi.mock("@/api/client", () => ({
  default: { get: (...args: unknown[]) => mockGet(...args) },
}));
vi.mock("@/api/photos", () => ({ photoUrl: (key: string) => `/photos/${key}` }));

describe.each(["swipe", "favorites", "archives"])("%s WC preview", (section) => {
  it.each([2, 0, null, undefined])("handles a WC count of %s", async (toilets) => {
    const listing = {
      id: 1, source: "pap", title: "Apartment", rooms: 3, toilets, photos: [],
    };
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/auth/me")) {
        return Promise.resolve({ data: { has_api_key: true, has_gmail_token: true } });
      }
      if (url.includes("/archives")) {
        return Promise.resolve({ data: {
          archives: [{ listing, passed_at: "2026-10-13T12:00:00Z" }], total: 1,
        } });
      }
      return Promise.resolve({ data: { listings: [listing], remaining: 1 } });
    });
    const view = section === "swipe" ? <Swipe /> : section === "archives" ? <Archives /> : (
      <KanbanCard item={{
        id: 1, listing, comment_count: 0, has_visit_date: false,
        status: "to_contact", owner: null, created_at: "2026-10-13T12:00:00Z",
      }} />
    );
    renderWithProviders(view, { token: "test" });
    expect(await screen.findByText("Apartment")).toBeInTheDocument();
    expect(screen.getAllByText("3 p.").length).toBeGreaterThan(0);
    if (toilets == null) {
      expect(screen.queryByText(/ WC$/)).not.toBeInTheDocument();
    } else {
      expect(screen.getAllByText(`${toilets} WC`).length).toBeGreaterThan(0);
    }
  });
});
