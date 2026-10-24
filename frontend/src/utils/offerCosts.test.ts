import { estimateOfferCosts, parseEuroCents } from "./offerCosts";

describe("offer cost estimates", () => {
  it("calculates a €500,000 Paris purchase with €50,000 travaux", () => {
    expect(estimateOfferCosts(50_000_000, 5_000_000)).toEqual({
      transferTaxes: 3_159_250,
      securityContribution: 50_000,
      notaryFee: 439_225,
      notaryVat: 87_845,
      formalities: 96_000,
      disbursements: 60_000,
      acquisitionFees: 3_892_320,
      total: 58_892_320,
    });
  });

  it.each([
    [650_000, 25_155],
    [1_700_000, 41_913],
    [6_000_000, 87_665],
    [6_100_000, 88_464],
  ])("applies marginal notary bands at %i cents", (price, notaryFee) => {
    expect(estimateOfferCosts(price, 0).notaryFee).toBe(notaryFee);
  });

  it("adds works once without taxing them or counting agency fees twice", () => {
    const withoutWorks = estimateOfferCosts(50_000_000, 0);
    const withWorks = estimateOfferCosts(50_000_000, 1_234_567);
    expect(withWorks.acquisitionFees).toBe(withoutWorks.acquisitionFees);
    expect(withWorks.total - withoutWorks.total).toBe(1_234_567);
    expect(withoutWorks.total).toBe(50_000_000 + withoutWorks.acquisitionFees);
  });

  it("applies the minimum registration contribution", () => {
    expect(estimateOfferCosts(650_000, 0).securityContribution).toBe(1500);
  });

  it.each(["", "-1", "NaN", "Infinity", "1e5", "12.345", "10000000000"])("rejects invalid input %s", (value) => {
    expect(parseEuroCents(value)).toBeNull();
  });

  it("preserves cents and explicit zero", () => {
    expect(parseEuroCents("123456.78")).toBe(12_345_678);
    expect(parseEuroCents("0")).toBe(0);
    expect(parseEuroCents("1.2")).toBe(120);
    expect(parseEuroCents("9999999999.99")).toBe(999_999_999_999);
  });

  it.each([[0, 0], [-1, 0], [100, -1], [NaN, 0], [100, Infinity], [1.5, 0]])("rejects invalid calculation inputs", (offer, works) => {
    expect(() => estimateOfferCosts(offer, works)).toThrow(RangeError);
  });
});
