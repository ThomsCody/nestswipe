# Favorite offer budget

Verified on 19 October 2026. The favorite detail page saves the offer (FAI) and
estimated post-purchase works (TTC) as nullable `NUMERIC(12,2)` amounts, shared by
the household. PATCH distinguishes omitted values from explicit nulls. Migration
020 must run before deploying the updated backend. The frontend calculates an
indicative budget; it does not submit an offer or change the favorite's status.

## Scope and assumptions

The two-input estimate assumes an ordinary existing residential property in
Paris, at the standard departmental rate of 5%, without first-time-buyer relief.
This is an explicit scenario, not a determination of the property's tax regime.
It is not suitable for new-build/VEFA purchases, special exemptions or other
local rates. The temporary departmental increase ends on 31 March 2028; review
the rate before that date. Eligible first-time main-residence buyers are exempt
from the increase; mixed-eligibility joint purchases need individual assessment.

FAI includes agency fees, so the total never adds them again. With only FAI as
input, the full offer is used as the fee base: no agency fee or furniture deduction
is invented. Separately payable buyer agency fees may lower the taxable base.
Future works are added to the budget, not the acquisition fee base. Blank works
remain unknown: the UI labels the result **Total before travaux**; explicit zero
means no works budget.

## Calculation

For an offer P:

| Component | Calculation |
| --- | --- |
| Departmental transfer tax | P × 5% |
| Municipal transfer tax | P × 1.2% |
| Collection charge | (P × 5%) × 2.37%, giving total transfer taxes of P × 6.3185% before rounding |
| Property registration contribution | max(P × 0.1%, €15) |
| Notary sale fee, before VAT | Marginal bands: 3.870% to €6,500; 1.596% from €6,500 to €17,000; 1.064% from €17,000 to €60,000; 0.799% above €60,000 |
| VAT on sale fee | 20% |
| Formalities budget | €800 before VAT + €160 VAT = €960 |
| Disbursements budget | €600 |

The €1,560 allowance follows the formalities/debours assumptions shown in Paris
notaries' published calculator examples. It is a budgeting choice, not a legally
fixed charge. Actual formalities vary by deed. No discretionary fee discount is
assumed. Financing (interest, guarantees, insurance), tax/co-ownership adjustments
and moving costs are excluded. Final fees must be confirmed by the notary.

Calculations use integer cents and round each component to cents. The acquisition
fee is the sum of the components; total = offer + acquisition fee + works.
All displayed monetary amounts are rounded to the nearest whole euro; underlying
calculations retain cents. Independently rounded rows can differ from the displayed
total by a euro. This is not a reproduction of the tax office's final assessment rounding.

Example: €500,000 FAI + €50,000 works gives €31,592.50 transfer taxes, €500
registration contribution, €4,392.25 notary fee + €878.45 VAT, and €1,560
allowances. Acquisition fees: **€38,923.20**. Total budget: **€588,923.20**.

## Primary sources

- [French tax authority: acquisition taxes, CSI minimum and notary bands](https://www.impots.gouv.fr/particulier/questions/jachete-un-bien-immobilier-quaurai-je-payer-comme-frais-au-notaire), updated 17 July 2026.
- [Paris notaries: 5% departmental rate and first-time-buyer exception](https://paris.notaires.fr/fr/actualites/ventes-immobilieres-augmentation-des-droits-denregistrement-dans-le-grand-paris).
- [Service Public: notary fees and VAT](https://www.service-public.gouv.fr/particuliers/vosdroits/F17701).
- [Paris notaries: example calculator output](https://paris.notaires.fr/fr/outils-et-services/calcul-de-frais-d-achat/resultat/5026322/pdf), indexed output showing €800 formalities before VAT and €600 disbursements; generated links may expire.
- [Notaires de France: different treatment for eligible new-build purchases](https://www.notaires.fr/fr/immobilier-fiscalite/financement/acquerir-en-frais-de-notaire-reduits).
