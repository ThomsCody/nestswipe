// Existing-property estimate, Paris standard rate, verified 2026-10-19.
// Sources and limitations: docs/offer-cost-estimate.md.
// Money is calculated in integer cents; only the UI converts it to euros.
export const MAX_AMOUNT_CENTS = 999_999_999_999;

export function parseEuroCents(value: string): number | null {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return null;
  const [euros, cents = ""] = value.split(".");
  const result = Number(euros) * 100 + Number(cents.padEnd(2, "0"));
  return Number.isSafeInteger(result) && result <= MAX_AMOUNT_CENTS ? result : null;
}

export function estimateOfferCosts(offerCents: number, renovationCents: number) {
  if (!Number.isSafeInteger(offerCents) || offerCents <= 0 || offerCents > MAX_AMOUNT_CENTS ||
      !Number.isSafeInteger(renovationCents) || renovationCents < 0 || renovationCents > MAX_AMOUNT_CENTS) {
    throw new RangeError("Invalid offer or renovation amount");
  }

  const departmentalTax = Math.round(offerCents * 5 / 100);
  const municipalTax = Math.round(offerCents * 12 / 1000);
  // 2.37% of the departmental levy, i.e. 0.1185% of the price.
  const collectionTax = Math.round(offerCents * 1185 / 1_000_000);
  const transferTaxes = departmentalTax + municipalTax + collectionTax;
  const securityContribution = Math.max(1500, Math.round(offerCents / 1000));

  const bands: [number, number][] = [
    [650_000, 3870],
    [1_700_000, 1596],
    [6_000_000, 1064],
    [MAX_AMOUNT_CENTS, 799],
  ];
  let lower = 0;
  let notaryFeeUnrounded = 0;
  for (const [upper, rate] of bands) {
    notaryFeeUnrounded += Math.max(0, Math.min(offerCents, upper) - lower) * rate / 100_000;
    lower = upper;
  }
  const notaryFee = Math.round(notaryFeeUnrounded);
  const notaryVat = Math.round(notaryFee / 5);
  // Budget allowances, not statutory flat charges: €800 HT formalities + VAT, €600 disbursements.
  const formalities = 96_000;
  const disbursements = 60_000;
  const acquisitionFees = transferTaxes + securityContribution + notaryFee + notaryVat + formalities + disbursements;
  return {
    transferTaxes, securityContribution, notaryFee, notaryVat, formalities,
    disbursements, acquisitionFees,
    total: offerCents + renovationCents + acquisitionFees,
  };
}
