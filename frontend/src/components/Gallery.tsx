import { useState, useEffect, useCallback, useRef } from "react";
import { photoUrl } from "@/api/photos";
import type { Listing } from "@/types";

/* ------------------------------------------------------------------ */
/*  Lightbox                                                          */
/* ------------------------------------------------------------------ */

function Lightbox({
  photos,
  index,
  onClose,
  onChangeIndex,
}: {
  photos: Listing["photos"];
  index: number;
  onClose: () => void;
  onChangeIndex: (i: number) => void;
}) {
  const touchStartX = useRef<number | null>(null);

  const goPrev = useCallback(() => {
    onChangeIndex((index - 1 + photos.length) % photos.length);
  }, [index, photos.length, onChangeIndex]);

  const goNext = useCallback(() => {
    onChangeIndex((index + 1) % photos.length);
  }, [index, photos.length, onChangeIndex]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); }
      else if (e.key === "ArrowLeft") { e.stopPropagation(); goPrev(); }
      else if (e.key === "ArrowRight") { e.stopPropagation(); goNext(); }
    };
    // Use capture phase so this fires before any bubble-phase listeners (e.g. swipe pass/like)
    window.addEventListener("keydown", handleKey, true);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleKey, true);
      document.body.style.overflow = "";
    };
  }, [onClose, goPrev, goNext]);

  const onTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0]!.clientX;
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null) return;
    const dx = e.changedTouches[0]!.clientX - touchStartX.current;
    if (Math.abs(dx) > 50) {
      dx < 0 ? goNext() : goPrev();
    }
    touchStartX.current = null;
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 text-white/70 hover:text-white z-10"
      >
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      <span className="absolute top-4 left-4 text-white/70 text-sm">
        {index + 1} / {photos.length}
      </span>

      {photos.length > 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); goPrev(); }}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-white/60 hover:text-white p-2"
        >
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      <img
        src={photoUrl(photos[index]!.s3_key)}
        alt=""
        className="max-h-[90vh] max-w-[90vw] object-contain select-none"
        onClick={(e) => e.stopPropagation()}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
        draggable={false}
      />

      {photos.length > 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); goNext(); }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-white/60 hover:text-white p-2"
        >
          <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Gallery                                                           */
/* ------------------------------------------------------------------ */

interface GalleryProps {
  photos: Listing["photos"];
  heightClass?: string;
}

export default function Gallery({ photos, heightClass = "h-72" }: GalleryProps) {
  const [selected, setSelected] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const touchStartX = useRef<number | null>(null);
  if (!photos.length) return null;

  const goPrev = () => setSelected((i) => (i - 1 + photos.length) % photos.length);
  const goNext = () => setSelected((i) => (i + 1) % photos.length);

  const onTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0]!.clientX;
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX.current === null) return;
    const dx = e.changedTouches[0]!.clientX - touchStartX.current;
    if (Math.abs(dx) > 50) {
      dx < 0 ? goNext() : goPrev();
    }
    touchStartX.current = null;
  };

  return (
    <div>
      <div
        className={`relative ${heightClass} bg-gray-900 rounded-lg overflow-hidden mb-2 cursor-pointer`}
        onClick={() => setLightboxOpen(true)}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <img
          src={photoUrl(photos[selected]!.s3_key)}
          alt=""
          className="w-full h-full object-contain"
        />
        {photos.length > 1 && (
          <>
            <button
              onClick={(e) => { e.stopPropagation(); goPrev(); }}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/70"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); goNext(); }}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/70"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <span className="absolute bottom-2 left-1/2 -translate-x-1/2 text-white/70 text-xs bg-black/50 px-2 py-0.5 rounded-full">
              {selected + 1} / {photos.length}
            </span>
          </>
        )}
      </div>
      {photos.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-2">
          {photos.map((p, i) => (
            <button
              key={p.id}
              onClick={() => setSelected(i)}
              className={`flex-shrink-0 w-16 h-16 rounded overflow-hidden border-2 ${
                i === selected ? "border-indigo-500" : "border-transparent"
              }`}
            >
              <img
                src={photoUrl(p.s3_key)}
                alt=""
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      )}
      {lightboxOpen && (
        <Lightbox
          photos={photos}
          index={selected}
          onClose={() => setLightboxOpen(false)}
          onChangeIndex={setSelected}
        />
      )}
    </div>
  );
}
