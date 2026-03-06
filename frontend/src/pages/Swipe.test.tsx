import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import Swipe from "./Swipe";
import { renderWithProviders } from "@/test/utils";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/api/client", () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

vi.mock("@/api/photos", () => ({
  photoUrl: (key: string) => `/photos/${key}`,
}));

const LISTING = {
  id: 1,
  source: "seloger",
  title: "Bel appartement",
  price: 450000,
  sqm: 65,
  price_per_sqm: 6923,
  photos: [{ id: 1, s3_key: "photo1.jpg", position: 0 }],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Swipe", () => {
  it("shows loading state", () => {
    // Never resolve the query to stay in loading
    mockGet.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Swipe />, { token: "t" });
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows 'all caught up' when queue is empty and setup is complete", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/auth/me")) {
        return Promise.resolve({ data: { has_api_key: true, has_gmail_token: true } });
      }
      return Promise.resolve({ data: { listings: [], remaining: 0 } });
    });

    renderWithProviders(<Swipe />, { token: "t" });
    await waitFor(() => {
      expect(screen.getByText("All caught up!")).toBeInTheDocument();
    });
  });

  it("shows setup needed when gmail token is missing", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/auth/me")) {
        return Promise.resolve({ data: { has_api_key: true, has_gmail_token: false } });
      }
      return Promise.resolve({ data: { listings: [], remaining: 0 } });
    });

    renderWithProviders(<Swipe />, { token: "t" });
    await waitFor(() => {
      expect(screen.getByText("Setup needed")).toBeInTheDocument();
      expect(screen.getByText(/Gmail is not connected/)).toBeInTheDocument();
    });
  });

  it("shows setup needed when API key is missing", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/auth/me")) {
        return Promise.resolve({ data: { has_api_key: false, has_gmail_token: true } });
      }
      return Promise.resolve({ data: { listings: [], remaining: 0 } });
    });

    renderWithProviders(<Swipe />, { token: "t" });
    await waitFor(() => {
      expect(screen.getByText("Setup needed")).toBeInTheDocument();
      expect(screen.getByText(/OpenAI API key missing/)).toBeInTheDocument();
    });
  });

  it("renders listing card with like and pass buttons", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/auth/me")) {
        return Promise.resolve({ data: { has_api_key: true, has_gmail_token: true } });
      }
      return Promise.resolve({ data: { listings: [LISTING], remaining: 1 } });
    });

    renderWithProviders(<Swipe />, { token: "t" });
    await waitFor(() => {
      expect(screen.getByText("Bel appartement")).toBeInTheDocument();
    });
    expect(screen.getByText("Like")).toBeInTheDocument();
    expect(screen.getByText("Pass")).toBeInTheDocument();
  });

  it("calls swipe mutation on like button click", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/auth/me")) {
        return Promise.resolve({ data: { has_api_key: true, has_gmail_token: true } });
      }
      return Promise.resolve({ data: { listings: [LISTING], remaining: 1 } });
    });
    mockPost.mockResolvedValue({ data: {} });

    renderWithProviders(<Swipe />, { token: "t" });
    await waitFor(() => {
      expect(screen.getByText("Like")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText("Like"));
    expect(mockPost).toHaveBeenCalledWith("/listings/1/swipe", { action: "like" });
  });

  it("calls swipe mutation on pass button click", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/auth/me")) {
        return Promise.resolve({ data: { has_api_key: true, has_gmail_token: true } });
      }
      return Promise.resolve({ data: { listings: [LISTING], remaining: 1 } });
    });
    mockPost.mockResolvedValue({ data: {} });

    renderWithProviders(<Swipe />, { token: "t" });
    await waitFor(() => {
      expect(screen.getByText("Pass")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText("Pass"));
    expect(mockPost).toHaveBeenCalledWith("/listings/1/swipe", { action: "pass" });
  });
});
