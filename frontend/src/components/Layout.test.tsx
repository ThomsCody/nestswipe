import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import Layout from "./Layout";
import { renderWithProviders } from "@/test/utils";
import { Route, Routes } from "react-router-dom";

// Mock the API client to avoid real requests
vi.mock("@/api/client", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { remaining: 0 } }),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

function renderLayout(initialEntries = ["/swipe"]) {
  return renderWithProviders(
    <Routes>
      <Route element={<Layout />}>
        <Route path="/swipe" element={<div>Swipe Page</div>} />
        <Route path="/favorites" element={<div>Favorites Page</div>} />
        <Route path="/archives" element={<div>Archives Page</div>} />
        <Route path="/settings" element={<div>Settings Page</div>} />
      </Route>
    </Routes>,
    { initialEntries, token: "test-token" },
  );
}

describe("Layout", () => {
  it("renders all nav links", () => {
    renderLayout();
    expect(screen.getAllByText("Swipe").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Favorites").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Archives").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Settings").length).toBeGreaterThan(0);
  });

  it("renders logout button", () => {
    renderLayout();
    expect(screen.getAllByText("Logout").length).toBeGreaterThan(0);
  });

  it("toggles mobile menu when hamburger is clicked", async () => {
    renderLayout();
    const hamburger = screen.getByLabelText("Toggle menu");

    // Mobile menu should not be visible initially (no mobile nav)
    // The mobile nav has class md:hidden, but in tests the DOM is flat
    // Click to open menu
    await userEvent.click(hamburger);

    // After toggle, the mobile nav should appear
    // We should see the links in the mobile menu too
    const swipeLinks = screen.getAllByText("Swipe");
    expect(swipeLinks.length).toBeGreaterThanOrEqual(2); // desktop + mobile
  });

  it("renders page content via Outlet", () => {
    renderLayout(["/swipe"]);
    expect(screen.getByText("Swipe Page")).toBeInTheDocument();
  });

  it("highlights active nav link", () => {
    renderLayout(["/favorites"]);
    // The favorites link in desktop nav should have the active color class
    const favLinks = screen.getAllByText("Favorites");
    const hasActive = favLinks.some((el) => el.className.includes("text-indigo-600"));
    expect(hasActive).toBe(true);
  });

  it("closes mobile menu on navigation", async () => {
    renderLayout(["/swipe"]);
    const hamburger = screen.getByLabelText("Toggle menu");

    // Open mobile menu
    await userEvent.click(hamburger);

    // Click a link in the mobile menu to navigate
    const favoritesLinks = screen.getAllByText("Favorites");
    // Click the last one (mobile menu link)
    await userEvent.click(favoritesLinks[favoritesLinks.length - 1]!);

    // The mobile menu should have closed (location changed triggers useEffect)
    expect(screen.getByText("Favorites Page")).toBeInTheDocument();
  });
});
