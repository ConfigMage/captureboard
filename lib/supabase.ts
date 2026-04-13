import { createClient, SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

// Lazy-init to avoid crashing at build time when env vars aren't set
let _client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (!_client) {
    if (!url || !key) {
      throw new Error("Supabase env vars not configured");
    }
    _client = createClient(url, key);
  }
  return _client;
}

// Default export for convenience — only use in client components at runtime
export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop) {
    return Reflect.get(getSupabase(), prop);
  },
});
