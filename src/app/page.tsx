"use client";

import { useCallback, useEffect, useState } from "react";
import { supabase } from "../../lib/supabase";
import type { Category, Item, Status } from "../../lib/types";

const CATEGORIES: { label: string; value: Category | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Movies", value: "movie" },
  { label: "TV", value: "tv" },
  { label: "Books", value: "book" },
  { label: "Podcasts", value: "podcast" },
  { label: "Articles", value: "article" },
  { label: "Music", value: "music" },
  { label: "Misc", value: "misc" },
];

const STATUSES: { label: string; value: Status | "all" }[] = [
  { label: "All", value: "all" },
  { label: "New", value: "new" },
  { label: "Started", value: "started" },
  { label: "Done", value: "done" },
];

const CATEGORY_COLORS: Record<string, string> = {
  movie: "bg-purple-500/20 text-purple-400",
  tv: "bg-blue-500/20 text-blue-400",
  book: "bg-amber-500/20 text-amber-400",
  podcast: "bg-green-500/20 text-green-400",
  article: "bg-rose-500/20 text-rose-400",
  music: "bg-cyan-500/20 text-cyan-400",
  misc: "bg-gray-500/20 text-gray-400",
};

const STATUS_COLORS: Record<string, string> = {
  new: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  started: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  done: "bg-green-500/20 text-green-400 border-green-500/30",
  skipped: "bg-gray-500/20 text-gray-400 border-gray-500/30",
};

const NEXT_STATUS: Record<Status, Status> = {
  new: "started",
  started: "done",
  done: "new",
  skipped: "new",
};

function timeAgo(dateStr: string): string {
  const seconds = Math.floor(
    (Date.now() - new Date(dateStr).getTime()) / 1000
  );
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function DetailRow({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;
  const display = Array.isArray(value) ? value.join(", ") : String(value);
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-muted shrink-0">{label}:</span>
      <span className="text-foreground/80">{display}</span>
    </div>
  );
}

function ItemCard({
  item,
  onStatusChange,
}: {
  item: Item;
  onStatusChange: (id: string, status: Status) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isPending = item.status === ("pending" as Status);
  const details = (item.details || {}) as Record<string, unknown>;

  return (
    <div
      className="bg-card border border-card-border rounded-xl p-4 transition-all"
      onClick={() => !isPending && setExpanded(!expanded)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            {item.category && (
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${CATEGORY_COLORS[item.category] || CATEGORY_COLORS.misc}`}
              >
                {item.category}
              </span>
            )}
            <span className="text-xs text-muted">
              {timeAgo(item.created_at)}
            </span>
          </div>

          {isPending ? (
            <div className="flex items-center gap-2">
              <div className="h-4 w-4 border-2 border-muted border-t-accent rounded-full animate-spin" />
              <span className="text-sm text-muted">{item.raw_input}</span>
            </div>
          ) : (
            <>
              <h3 className="font-medium text-foreground leading-snug">
                {item.title || item.raw_input}
              </h3>
              {item.summary && (
                <p className="text-sm text-muted mt-1 leading-relaxed">
                  {item.summary}
                </p>
              )}
            </>
          )}
        </div>

        {!isPending && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onStatusChange(item.id, NEXT_STATUS[item.status]);
            }}
            className={`text-xs font-medium px-2.5 py-1 rounded-lg border shrink-0 transition-colors hover:brightness-125 ${STATUS_COLORS[item.status] || STATUS_COLORS.new}`}
          >
            {item.status}
          </button>
        )}
      </div>

      {expanded && (
        <div className="mt-4 pt-3 border-t border-card-border space-y-1.5">
          {Object.entries(details).map(([key, value]) => (
            <DetailRow
              key={key}
              label={key.replace(/_/g, " ")}
              value={value}
            />
          ))}
          {item.source_url && (
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-block mt-2 text-sm text-accent hover:underline"
            >
              View source &rarr;
            </a>
          )}
          {Object.keys(details).length === 0 && !item.source_url && (
            <p className="text-sm text-muted">No additional details.</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [items, setItems] = useState<Item[]>([]);
  const [category, setCategory] = useState<Category | "all">("all");
  const [status, setStatus] = useState<Status | "all">("all");
  const [loading, setLoading] = useState(true);

  const fetchItems = useCallback(async () => {
    let query = supabase
      .from("items")
      .select("*")
      .order("created_at", { ascending: false });

    if (category !== "all") {
      query = query.eq("category", category);
    }

    if (status !== "all") {
      query = query.eq("status", status);
    } else {
      query = query.in("status", ["new", "started", "done", "pending"]);
    }

    const { data } = await query;
    if (data) setItems(data as Item[]);
    setLoading(false);
  }, [category, status]);

  useEffect(() => {
    fetchItems();
    const interval = setInterval(fetchItems, 30000);
    return () => clearInterval(interval);
  }, [fetchItems]);

  async function handleStatusChange(id: string, newStatus: Status) {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, status: newStatus } : item
      )
    );

    const { error } = await supabase
      .from("items")
      .update({ status: newStatus })
      .eq("id", id);

    if (error) {
      fetchItems();
    }
  }

  const pendingCount = items.filter(
    (i) => i.status === ("pending" as Status)
  ).length;

  return (
    <main className="flex-1 max-w-lg mx-auto w-full px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Capture</h1>
        {pendingCount > 0 && (
          <p className="text-sm text-muted mt-1">
            {pendingCount} item{pendingCount > 1 ? "s" : ""} being
            researched...
          </p>
        )}
      </header>

      {/* Category tabs */}
      <div className="flex gap-1.5 overflow-x-auto pb-2 mb-3 -mx-4 px-4 scrollbar-hide">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.value}
            onClick={() => setCategory(cat.value)}
            className={`text-sm px-3 py-1.5 rounded-lg whitespace-nowrap transition-colors ${
              category === cat.value
                ? "bg-foreground/10 text-foreground font-medium"
                : "text-muted hover:text-foreground/70"
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Status filter */}
      <div className="flex gap-1.5 mb-5">
        {STATUSES.map((s) => (
          <button
            key={s.value}
            onClick={() => setStatus(s.value)}
            className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
              status === s.value
                ? "bg-foreground/10 text-foreground font-medium"
                : "text-muted hover:text-foreground/70"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Items list */}
      <div className="space-y-3">
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="h-6 w-6 border-2 border-muted border-t-accent rounded-full animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted">
              {category === "all"
                ? "Nothing captured yet."
                : `No ${category} items yet.`}
            </p>
          </div>
        ) : (
          items.map((item) => (
            <ItemCard
              key={item.id}
              item={item}
              onStatusChange={handleStatusChange}
            />
          ))
        )}
      </div>
    </main>
  );
}
