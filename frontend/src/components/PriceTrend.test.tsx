import { render, screen } from "@testing-library/react";
import PriceTrend from "./PriceTrend";
import type { PriceHistoryEntry } from "@/types";

describe("PriceTrend", () => {
  it("returns null when history is undefined", () => {
    const { container } = render(<PriceTrend />);
    expect(container.innerHTML).toBe("");
  });

  it("returns null when history has fewer than 2 entries", () => {
    const history: PriceHistoryEntry[] = [{ price: 300000, observed_at: "2025-01-01" }];
    const { container } = render(<PriceTrend history={history} />);
    expect(container.innerHTML).toBe("");
  });

  it("returns null when price is unchanged", () => {
    const history: PriceHistoryEntry[] = [
      { price: 300000, observed_at: "2025-01-01" },
      { price: 300000, observed_at: "2025-02-01" },
    ];
    const { container } = render(<PriceTrend history={history} />);
    expect(container.innerHTML).toBe("");
  });

  it("shows down arrow when price decreased", () => {
    const history: PriceHistoryEntry[] = [
      { price: 350000, observed_at: "2025-01-01" },
      { price: 300000, observed_at: "2025-02-01" },
    ];
    render(<PriceTrend history={history} />);
    expect(screen.getByText("↓")).toBeInTheDocument();
  });

  it("shows up arrow when price increased", () => {
    const history: PriceHistoryEntry[] = [
      { price: 300000, observed_at: "2025-01-01" },
      { price: 350000, observed_at: "2025-02-01" },
    ];
    render(<PriceTrend history={history} />);
    expect(screen.getByText("↑")).toBeInTheDocument();
  });

  it("applies green color for price decrease", () => {
    const history: PriceHistoryEntry[] = [
      { price: 350000, observed_at: "2025-01-01" },
      { price: 300000, observed_at: "2025-02-01" },
    ];
    render(<PriceTrend history={history} />);
    expect(screen.getByText("↓").className).toContain("text-green-600");
  });

  it("applies red color for price increase", () => {
    const history: PriceHistoryEntry[] = [
      { price: 300000, observed_at: "2025-01-01" },
      { price: 350000, observed_at: "2025-02-01" },
    ];
    render(<PriceTrend history={history} />);
    expect(screen.getByText("↑").className).toContain("text-red-600");
  });
});
