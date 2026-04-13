import { createClient } from "@supabase/supabase-js";

// Server client — uses service role key, bypasses RLS
export function getServiceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );
}
