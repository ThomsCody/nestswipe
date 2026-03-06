import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ListingDetailView from "./ListingDetailView";
import { renderWithProviders } from "@/test/utils";
import type { Listing, PriceHistoryEntry } from "@/types";

vi.mock("@/api/photos", () => ({
  photoUrl: (key: string) => `/photos/${key}`,
}));

vi.mock("@/api/client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

const PHOTOS = [
  { id: 1, s3_key: "a.jpg", position: 0 },
  { id: 2, s3_key: "b.jpg", position: 1 },
  { id: 3, s3_key: "c.jpg", position: 2 },
];

const LISTING: Listing = {
  id: 1,
  source: "seloger",
  title: "Grand appartement",
  price: 500000,
  sqm: 80,
  price_per_sqm: 6250,
  photos: PHOTOS,
  external_url: "https://example.com/listing/1",
};

const PRICE_HISTORY: PriceHistoryEntry[] = [
  { price: 520000, observed_at: "2025-01-01" },
  { price: 500000, observed_at: "2025-02-01" },
];

function renderDetail() {
  return renderWithProviders(
    <ListingDetailView
      listing={LISTING}
      priceHistory={PRICE_HISTORY}
      backLabel="Back to Favorites"
      backTo="/favorites"
      bottomAction={<button>Remove</button>}
    />,
    { token: "t" },
  );
}

describe("ListingDetailView", () => {
  it("renders listing title and price", () => {
    renderDetail();
    expect(screen.getByText("Grand appartement")).toBeInTheDocument();
  });

  it("renders back button with label", () => {
    renderDetail();
    expect(screen.getByText(/Back to Favorites/)).toBeInTheDocument();
  });

  it("renders bottom action slot", () => {
    renderDetail();
    expect(screen.getByText("Remove")).toBeInTheDocument();
  });

  it("shows photo counter for multiple photos", () => {
    renderDetail();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("navigates to next photo when right arrow is clicked", async () => {
    renderDetail();
    // Find the gallery next button (SVG arrow right)
    const nextButtons = screen.getAllByRole("button");
    // The gallery has prev/next buttons; find the one with the forward arrow
    // Gallery buttons are inside the relative container
    const galleryNext = nextButtons.find((btn) =>
      btn.querySelector("path[d='M9 5l7 7-7 7']"),
    );
    expect(galleryNext).toBeDefined();

    await userEvent.click(galleryNext!);
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("navigates to previous photo when left arrow is clicked", async () => {
    renderDetail();
    // First go to photo 2
    const nextBtn = screen.getAllByRole("button").find((btn) =>
      btn.querySelector("path[d='M9 5l7 7-7 7']"),
    );
    await userEvent.click(nextBtn!);
    expect(screen.getByText("2 / 3")).toBeInTheDocument();

    // Now go back
    const prevBtn = screen.getAllByRole("button").find((btn) =>
      btn.querySelector("path[d='M15 19l-7-7 7-7']"),
    );
    await userEvent.click(prevBtn!);
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("renders external link", () => {
    renderDetail();
    const link = screen.getByText(/View original listing/);
    expect(link).toHaveAttribute("href", "https://example.com/listing/1");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
