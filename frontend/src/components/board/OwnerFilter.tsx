interface Member {
  id: number;
  name: string;
  picture?: string;
}

interface OwnerFilterProps {
  members: Member[];
  currentUserId: number | undefined;
  value: number | null;
  onChange: (ownerId: number | null) => void;
}

export default function OwnerFilter({ members, currentUserId, value, onChange }: OwnerFilterProps) {
  const pill = (active: boolean) =>
    `px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
      active ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
    }`;

  // Put current user first
  const sorted = [...members].sort((a, b) => {
    if (a.id === currentUserId) return -1;
    if (b.id === currentUserId) return 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="flex flex-wrap gap-2">
      <button className={pill(value === null)} onClick={() => onChange(null)}>
        Tous
      </button>
      {sorted.map((m) => (
        <button key={m.id} className={pill(value === m.id)} onClick={() => onChange(m.id)}>
          {m.id === currentUserId ? "Moi" : m.name.split(" ")[0]}
        </button>
      ))}
    </div>
  );
}
