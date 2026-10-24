import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import client from "@/api/client";
import { estimateOfferCosts, parseEuroCents } from "@/utils/offerCosts";

interface OfferSectionProps {
  favoriteId: number;
  offerPrice: string | null;
  renovationBudget: string | null;
}

const euro = new Intl.NumberFormat("fr-FR", {
  style: "currency", currency: "EUR", useGrouping: true, minimumFractionDigits: 0, maximumFractionDigits: 0,
});
// Regular non-breaking spaces make thousands groups clear across browser fonts.
const formatMoney = (cents: number) => euro.formatToParts(cents / 100)
  .map((part) => part.type === "group" ? "\u00a0" : part.value).join("");
const money = (cents: number) => formatMoney(cents);
const costRowClass = "grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4";
const amountClass = "whitespace-nowrap text-right tabular-nums";
const inputClass = "min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:opacity-50";

export default function OfferSection({ favoriteId, offerPrice, renovationBudget }: OfferSectionProps) {
  const queryClient = useQueryClient();
  const [offer, setOffer] = useState(offerPrice ?? "");
  const [renovation, setRenovation] = useState(renovationBudget ?? "");
  const [expanded, setExpanded] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setOffer(offerPrice ?? "");
    setRenovation(renovationBudget ?? "");
  }, [offerPrice, renovationBudget]);

  const mutation = useMutation({
    mutationFn: () => client.patch(`/favorites/${favoriteId}`, {
      offer_price: offer || null,
      renovation_budget: renovation || null,
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["favorite", String(favoriteId)] });
      setSaved(true);
    },
  });

  const offerCents = parseEuroCents(offer);
  const renovationCents = renovation === "" ? 0 : parseEuroCents(renovation);
  const invalidOffer = offer !== "" && (offerCents === null || offerCents === 0);
  const invalidRenovation = renovationCents === null;
  const costs = offerCents !== null && offerCents > 0 && renovationCents !== null
    ? estimateOfferCosts(offerCents, renovationCents) : null;
  const dirty = (offer || null) !== offerPrice || (renovation || null) !== renovationBudget;

  return (
    <section className="border-t border-gray-100" aria-labelledby="offer-heading">
      <h2 id="offer-heading">
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="offer-panel"
          onClick={() => setExpanded(!expanded)}
          className="flex min-h-14 w-full items-center justify-between px-5 py-4 text-left text-lg font-semibold text-gray-950 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-500 sm:px-6"
        >
          Offer
          <svg aria-hidden="true" className={`h-5 w-5 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </h2>
      <div id="offer-panel" hidden={!expanded} className="px-5 pb-5 sm:px-6 sm:pb-6">
        <form onSubmit={(event) => {
          event.preventDefault();
          if (dirty && !invalidOffer && !invalidRenovation && !mutation.isPending) mutation.mutate();
        }} className="space-y-4">
          <div>
            <label htmlFor="offer-price" className="mb-1.5 block text-sm font-medium text-gray-700">Offer made (€ FAI)</label>
            <input id="offer-price" type="number" inputMode="decimal" min="0.01" max="9999999999.99" step="0.01"
              value={offer} disabled={mutation.isPending} aria-invalid={invalidOffer} aria-describedby="offer-price-help"
              onChange={(event) => { setOffer(event.target.value); setSaved(false); mutation.reset(); }} className={inputClass} />
            <p id="offer-price-help" className="mt-1 text-xs text-gray-500">Agency fees included.</p>
          </div>
          <div>
            <label htmlFor="renovation-budget" className="mb-1.5 block text-sm font-medium text-gray-700">Estimated travaux (€ TTC)</label>
            <input id="renovation-budget" type="number" inputMode="decimal" min="0" max="9999999999.99" step="0.01"
              value={renovation} disabled={mutation.isPending} aria-invalid={invalidRenovation} aria-describedby="renovation-help"
              onChange={(event) => { setRenovation(event.target.value); setSaved(false); mutation.reset(); }} className={inputClass} />
            <p id="renovation-help" className="mt-1 text-xs text-gray-500">Works after purchase, including VAT. Leave blank if not estimated.</p>
          </div>
          {(invalidOffer || invalidRenovation) && <p role="alert" className="text-sm text-red-600">Enter valid euro amounts with up to two decimal places. The offer must be positive; travaux can be zero.</p>}

          <div className="rounded-lg bg-indigo-50 p-4">
            <p className="text-xs leading-5 text-gray-600">Estimate for an existing property (ancien), Paris standard rate, without first-time-buyer relief.</p>
            {costs ? (
              <dl className="mt-3 space-y-3 text-sm" aria-live="polite">
                <div className={costRowClass}><dt>Offer FAI</dt><dd className={amountClass}>{money(offerCents!)}</dd></div>
                <div className={costRowClass}><dt>Travaux{renovation === "" ? " (not estimated)" : ""}</dt><dd className={amountClass}>{renovation === "" ? "—" : money(renovationCents!)}</dd></div>
                <div className={costRowClass}><dt>Frais de notaire (estimated)</dt><dd className={amountClass}>{money(costs.acquisitionFees)}</dd></div>
                <div className="border-t border-indigo-200 pt-3 text-indigo-950"><dt className="font-medium">{renovation === "" ? "Total before travaux" : "Total estimated cost"}</dt><dd className={`${amountClass} mt-1 text-xl font-semibold`}>{money(costs.total)}</dd></div>
              </dl>
            ) : <p className="mt-3 text-sm text-gray-600">Enter an offer to calculate acquisition fees and total cost.</p>}
          </div>

          <details className="text-xs leading-5 text-gray-600">
            <summary className="cursor-pointer font-medium text-indigo-700">How are the fees calculated?</summary>
            <div className="mt-3 space-y-3">
              <p>Calculated on the full FAI offer, excluding future travaux. No agency fee or furniture deduction is assumed. Separately payable buyer agency fees may reduce the taxable base; confirm with your notary.</p>
              <dl className="space-y-2">
                {[
                  ["Transfer taxes: 5% département + 1.2% commune + 2.37% of the departmental tax = 6.3185%", costs?.transferTaxes],
                  ["Property registration contribution: 0.1%, minimum €15", costs?.securityContribution],
                  ["Notary fee before VAT (tiered scale)", costs?.notaryFee],
                  ["VAT on notary fee: 20%", costs?.notaryVat],
                  ["Formalities allowance: €800 + €160 VAT", costs?.formalities],
                  ["Disbursements allowance: €600", costs?.disbursements],
                ].map(([label, amount]) => (
                  <div key={String(label)}><dt>{label}</dt>{typeof amount === "number" && <dd className={`${amountClass} font-medium text-gray-900`}>{money(amount)}</dd>}</div>
                ))}
              </dl>
              <p>Notary scale, before VAT: 3.870% up to €6,500; 1.596% from €6,500 to €17,000; 1.064% from €17,000 to €60,000; 0.799% above €60,000. Each rate applies only to its band.</p>
              <p>The €1,560 formalities and disbursements budget is an allowance, not a fixed legal charge. Actual fees depend on the deed. No negotiated notary discount is included.</p>
              <p>Rates checked on 19 October 2026. The temporary 5% departmental rate runs until 31 March 2028. First-time buyers, other departments and new-build purchases can have lower taxes.</p>
              <p>Total = offer FAI + acquisition fees + travaux. Excludes financing costs (interest, insurance, guarantees), tax and co-ownership adjustments, and moving costs. Confirm the final amount with your notary.</p>
              <p className="flex flex-wrap gap-x-3 gap-y-1">
                <a className="underline" href="https://www.impots.gouv.fr/particulier/questions/jachete-un-bien-immobilier-quaurai-je-payer-comme-frais-au-notaire" target="_blank" rel="noreferrer">Tax authority: rates and scale</a>
                <a className="underline" href="https://paris.notaires.fr/fr/actualites/ventes-immobilieres-augmentation-des-droits-denregistrement-dans-le-grand-paris" target="_blank" rel="noreferrer">Paris notaries: local rate</a>
              </p>
            </div>
          </details>
          <button type="submit" disabled={!dirty || invalidOffer || invalidRenovation || mutation.isPending}
            className="min-h-11 w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50">
            {mutation.isPending ? "Saving..." : "Save offer"}
          </button>
          {mutation.isError && <p role="alert" className="text-sm text-red-600">Could not save the offer. Your entries are still here; please try again.</p>}
          {saved && !dirty && <p role="status" className="text-sm text-green-700">Offer saved.</p>}
        </form>
      </div>
    </section>
  );
}
