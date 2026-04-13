export type Category =
  | "movie"
  | "tv"
  | "book"
  | "podcast"
  | "article"
  | "music"
  | "misc";

export type Status = "new" | "started" | "done" | "skipped";

export interface Item {
  id: string;
  raw_input: string;
  title: string | null;
  category: Category | null;
  summary: string | null;
  source_url: string | null;
  status: Status;
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MovieDetails {
  year?: number;
  director?: string;
  cast?: string[];
  genre?: string;
  where_to_watch?: string[];
  rating?: string;
}

export interface TvDetails {
  year?: number;
  director?: string;
  cast?: string[];
  genre?: string;
  where_to_watch?: string[];
  rating?: string;
}

export interface BookDetails {
  author?: string;
  genre?: string;
  page_count?: number;
  goodreads_rating?: number;
}

export interface PodcastDetails {
  show_name?: string;
  episode_title?: string;
  duration?: string;
  topics?: string[];
}

export interface ArticleDetails {
  author?: string;
  publication?: string;
  date_published?: string;
  key_takeaways?: string[];
}

export interface MusicDetails {
  artist?: string;
  album?: string;
  genre?: string;
  similar_to?: string[];
}
