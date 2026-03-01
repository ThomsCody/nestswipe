import type { PriceHistoryEntry } from "@/types";

export default function PriceTrend({ history }: { history?: PriceHistoryEntry[] }) {
  if (!history || history.length < 2) return null;

  const prev = history[history.length - 2]!;
  const last = history[history.length - 1]!;
  const decreased = last.price < prev.price;
  const increased = last.price > prev.price;

  if (!decreased && !increased) return null;

  return (
    <span className="relative group inline-flex items-center ml-1">
      <span
        className={`text-xs font-semibold ${decreased ? "text-green-600" : "text-red-600"}`}
      >
        {decreased ? "\u2193" : "\u2191"}
      </span>
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-50">
        <div className="bg-gray-900 text-white text-[11px] rounded-lg shadow-lg px-3 py-2 whitespace-nowrap">
          <table className="border-collapse">
            <thead>
              <tr>
                <th className="pr-3 text-left font-medium text-gray-400">Date</th>
                <th className="text-right font-medium text-gray-400">Price</th>
              </tr>
            </thead>
            <tbody>
              {history.map((entry, i) => (
                <tr key={i}>
                  <td className="pr-3 py-0.5">
                    {new Date(entry.observed_at).toLocaleDateString("fr-FR")}
                  </td>
                  <td className="text-right py-0.5">
                    {entry.price.toLocaleString("fr-FR")}&nbsp;&euro;
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </span>
  );
}
