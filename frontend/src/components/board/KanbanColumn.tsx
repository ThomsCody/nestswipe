import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import KanbanCard from "./KanbanCard";
import type { FavoriteItem, HouseholdMember } from "./KanbanCard";

export interface ColumnConfig {
  id: string;
  label: string;
  color: string;
  bg: string;
  ring: string;
}

interface KanbanColumnProps {
  config: ColumnConfig;
  items: FavoriteItem[];
  members?: HouseholdMember[];
  onOwnerChange?: (favoriteId: number, ownerId: number | null) => void;
}

export default function KanbanColumn({ config, items, members, onOwnerChange }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: config.id });

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col min-w-[280px] w-[320px] shrink-0 rounded-xl ${
        isOver ? "ring-2 ring-indigo-300" : ""
      }`}
    >
      <div className={`flex items-center gap-2 px-3 py-2 rounded-t-xl ${config.bg}`}>
        <span className={`w-2.5 h-2.5 rounded-full ${config.ring}`} />
        <h3 className={`text-sm font-semibold ${config.color}`}>{config.label}</h3>
        <span className={`ml-auto text-xs font-medium ${config.color} opacity-70`}>{items.length}</span>
      </div>
      <div className="flex-1 bg-gray-50 rounded-b-xl p-2 space-y-2 min-h-[120px]">
        <SortableContext items={items.map((i) => i.id)} strategy={verticalListSortingStrategy}>
          {items.map((item) => (
            <KanbanCard key={item.id} item={item} members={members} onOwnerChange={onOwnerChange} />
          ))}
        </SortableContext>
      </div>
    </div>
  );
}
