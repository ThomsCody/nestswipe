import {
  DndContext,
  DragOverlay,
  PointerSensor,
  TouchSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
  type DragOverEvent,
} from "@dnd-kit/core";
import { useState } from "react";
import KanbanColumn from "./KanbanColumn";
import KanbanCard from "./KanbanCard";
import type { FavoriteItem, HouseholdMember } from "./KanbanCard";
import type { ColumnConfig } from "./KanbanColumn";

const ARCHIVE_ID = "__archive__";

const COLUMNS: ColumnConfig[] = [
  {
    id: "to_contact",
    label: "A contacter",
    color: "text-blue-700",
    bg: "bg-blue-50",
    ring: "bg-blue-500",
  },
  {
    id: "visit_planned",
    label: "Visite pr\u00e9vue",
    color: "text-amber-700",
    bg: "bg-amber-50",
    ring: "bg-amber-500",
  },
  {
    id: "offer_made",
    label: "Offre faite",
    color: "text-emerald-700",
    bg: "bg-emerald-50",
    ring: "bg-emerald-500",
  },
];

function ArchiveDropZone({ visible }: { visible: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: ARCHIVE_ID });

  return (
    <div
      ref={setNodeRef}
      className={`flex items-center justify-center gap-2 rounded-xl border-2 border-dashed transition-all duration-200 ${
        visible ? "h-16 opacity-100 mt-4" : "h-0 opacity-0 overflow-hidden"
      } ${isOver ? "border-red-400 bg-red-50 text-red-600" : "border-gray-300 bg-gray-50 text-gray-400"}`}
    >
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
      </svg>
      <span className="text-sm font-medium">{isOver ? "Retirer des favoris" : "Glisser ici pour archiver"}</span>
    </div>
  );
}

interface KanbanBoardProps {
  items: FavoriteItem[];
  members?: HouseholdMember[];
  onStatusChange: (favoriteId: number, newStatus: string) => void;
  onArchive: (favoriteId: number) => void;
  onOwnerChange: (favoriteId: number, ownerId: number | null) => void;
}

export default function KanbanBoard({ items, members, onStatusChange, onArchive, onOwnerChange }: KanbanBoardProps) {
  const [activeItem, setActiveItem] = useState<FavoriteItem | null>(null);

  const pointerSensor = useSensor(PointerSensor, {
    activationConstraint: { distance: 8 },
  });
  const touchSensor = useSensor(TouchSensor, {
    activationConstraint: { delay: 250, tolerance: 5 },
  });
  const sensors = useSensors(pointerSensor, touchSensor);

  const grouped = COLUMNS.map((col) => ({
    config: col,
    items: items.filter((i) => i.status === col.id),
  }));

  function handleDragStart(event: DragStartEvent) {
    const item = items.find((i) => i.id === event.active.id);
    setActiveItem(item ?? null);
  }

  function handleDragOver(_event: DragOverEvent) {
    // Could implement preview here in the future
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveItem(null);
    const { active, over } = event;
    if (!over) return;

    const favoriteId = active.id as number;

    // Dropped on archive zone
    if (over.id === ARCHIVE_ID) {
      onArchive(favoriteId);
      return;
    }

    // Determine target column: either dropped on a column (droppable) or on a card
    let targetStatus: string | undefined;
    const overColumn = COLUMNS.find((c) => c.id === over.id);
    if (overColumn) {
      targetStatus = overColumn.id;
    } else {
      // Dropped on a card — find which column that card is in
      const overItem = items.find((i) => i.id === over.id);
      if (overItem) targetStatus = overItem.status;
    }

    if (!targetStatus) return;

    const draggedItem = items.find((i) => i.id === favoriteId);
    if (!draggedItem || draggedItem.status === targetStatus) return;

    onStatusChange(favoriteId, targetStatus);
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto pb-4 -mx-4 px-4">
        {grouped.map(({ config, items }) => (
          <KanbanColumn key={config.id} config={config} items={items} members={members} onOwnerChange={onOwnerChange} />
        ))}
      </div>
      <ArchiveDropZone visible={activeItem !== null} />
      <DragOverlay dropAnimation={null}>
        {activeItem ? (
          <div className="w-[300px] rotate-2 opacity-90">
            <KanbanCard item={activeItem} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
