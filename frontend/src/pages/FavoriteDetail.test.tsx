import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import client from "@/api/client";
import { renderWithProviders } from "@/test/utils";
import FavoriteDetail from "./FavoriteDetail";

vi.mock("@/api/client", () => ({ default: { get: vi.fn(), patch: vi.fn() } }));
vi.mock("@/api/photos", () => ({ photoUrl: (key: string) => `/photos/${key}` }));

function setup(offer: string | null = null, works: string | null = null) {
  let favorite = {
    id: 42, listing: { id: 1, title: "Paris apartment", source: "pap", price: 550000, photos: [] },
    comments: [], price_history: [], status: "to_contact", owner: null, created_at: "2026-10-19",
    visit_date: null, location: null, seller_name: null, seller_phone: null, seller_is_agency: false,
    offer_price: offer, renovation_budget: works,
  };
  vi.mocked(client.get).mockImplementation(async (url) => ({ data:
    url === "/favorites/42" ? { ...favorite } :
      url === "/household" ? { members: [] } :
        url === "/favorites/statuses" ? [{ id: "to_contact", label: "À contacter" }] : { id: 1, name: "Thomas" },
  }));
  vi.mocked(client.patch).mockImplementation(async (_url, payload) => {
    favorite = { ...favorite, ...payload as Partial<typeof favorite> };
    return { data: favorite };
  });
  return renderWithProviders(<Routes><Route path="/favorites/:id" element={<FavoriteDetail />} /></Routes>, {
    initialEntries: ["/favorites/42"], token: "t",
  });
}

beforeEach(() => vi.resetAllMocks());

function saveOffer() {
  // happy-dom incorrectly checks decimal steps with floating-point modulo.
  // Submit the form directly; separate tests exercise our cent validation.
  fireEvent.submit(screen.getByRole("button", { name: "Save offer" }).closest("form")!);
}

it("starts collapsed between contact controls and remove from favorites", async () => {
  setup();
  const toggle = await screen.findByRole("button", { name: "Offer" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByLabelText("Offer made (€ FAI)")).not.toBeVisible();
  const saveContact = screen.getByRole("button", { name: "Save changes" });
  const remove = screen.getByRole("button", { name: "Remove from favorites" });
  expect(saveContact.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(toggle.compareDocumentPosition(remove) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await userEvent.click(toggle);
  expect(screen.getByLabelText("Offer made (€ FAI)")).toBeVisible();
});

it("calculates live, saves to the favorite and restores both fields on a new visit", async () => {
  const { unmount } = setup();
  await userEvent.click(await screen.findByRole("button", { name: "Offer" }));
  fireEvent.change(screen.getByLabelText("Offer made (€ FAI)"), { target: { value: "500000" } });
  expect(screen.getByText("Total before travaux")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Estimated travaux (€ TTC)"), { target: { value: "50000" } });
  expect(screen.getByText("Total estimated cost").nextElementSibling?.textContent?.replace(/\s/g, "")).toBe("588923€");
  saveOffer();
  await screen.findByText("Offer saved.");
  expect(client.patch).toHaveBeenCalledWith("/favorites/42", { offer_price: "500000", renovation_budget: "50000" });
  unmount();
  renderWithProviders(<Routes><Route path="/favorites/:id" element={<FavoriteDetail />} /></Routes>, { initialEntries: ["/favorites/42"], token: "t" });
  await userEvent.click(await screen.findByRole("button", { name: "Offer" }));
  expect(screen.getByLabelText("Offer made (€ FAI)")).toHaveValue(500000);
  expect(screen.getByLabelText("Estimated travaux (€ TTC)")).toHaveValue(50000);
});

it("allows explicit zero travaux and clearing saved amounts", async () => {
  setup("500000.00", "0.00");
  await userEvent.click(await screen.findByRole("button", { name: "Offer" }));
  expect(screen.getByText("Total estimated cost")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Offer made (€ FAI)"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("Estimated travaux (€ TTC)"), { target: { value: "" } });
  saveOffer();
  await waitFor(() => expect(client.patch).toHaveBeenCalledWith("/favorites/42", { offer_price: null, renovation_budget: null }));
});

it("keeps inputs after a failed save and supports retry", async () => {
  setup();
  vi.mocked(client.patch).mockRejectedValueOnce(new Error("Offline"));
  await userEvent.click(await screen.findByRole("button", { name: "Offer" }));
  fireEvent.change(screen.getByLabelText("Offer made (€ FAI)"), { target: { value: "500000" } });
  saveOffer();
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save");
  expect(screen.getByLabelText("Offer made (€ FAI)")).toHaveValue(500000);
  saveOffer();
  await screen.findByText("Offer saved.");
});

it("saving an offer preserves unsaved contact edits", async () => {
  setup();
  await userEvent.click(await screen.findByRole("button", { name: "Offer" }));
  fireEvent.change(screen.getByPlaceholderText("Name"), { target: { value: "Unsaved contact" } });
  fireEvent.change(screen.getByLabelText("Offer made (€ FAI)"), { target: { value: "500000" } });
  saveOffer();
  await screen.findByText("Offer saved.");
  expect(screen.getByPlaceholderText("Name")).toHaveValue("Unsaved contact");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
});

it("rejects negative and over-precision amounts and shows the fee assumptions", async () => {
  setup();
  await userEvent.click(await screen.findByRole("button", { name: "Offer" }));
  fireEvent.change(screen.getByLabelText("Offer made (€ FAI)"), { target: { value: "-1" } });
  expect(screen.getByRole("button", { name: "Save offer" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Offer made (€ FAI)"), { target: { value: "500000" } });
  fireEvent.change(screen.getByLabelText("Estimated travaux (€ TTC)"), { target: { value: "1.234" } });
  expect(screen.getByRole("button", { name: "Save offer" })).toBeDisabled();
  await userEvent.click(screen.getByText("How are the fees calculated?"));
  const section = screen.getByRole("region", { name: "Offer" });
  expect(within(section).getByText(/6.3185%/)).toBeVisible();
  expect(within(section).getByRole("link", { name: "Tax authority: rates and scale" })).toHaveAttribute("href", expect.stringContaining("impots.gouv.fr"));
});
