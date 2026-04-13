import { NextRequest, NextResponse } from "next/server";
import { getServiceClient } from "../../../../lib/supabase-server";

export async function POST(request: NextRequest) {
  try {
    const secret = request.headers.get("x-webhook-secret");
    if (secret !== process.env.WEBHOOK_SECRET) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const text = body.text;

    if (!text || typeof text !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'text' field" },
        { status: 400 }
      );
    }

    const supabase = getServiceClient();

    const { data, error } = await supabase
      .from("items")
      .insert({ raw_input: text, status: "pending" })
      .select("id")
      .single();

    if (error) {
      console.error("Supabase insert error:", error);
      return NextResponse.json(
        { error: "Failed to save item" },
        { status: 500 }
      );
    }

    // Fire GitHub repository_dispatch to trigger research
    const githubToken = process.env.GITHUB_TOKEN;
    const githubRepo = process.env.GITHUB_REPO;

    if (githubToken && githubRepo) {
      try {
        await fetch(
          `https://api.github.com/repos/${githubRepo}/dispatches`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${githubToken}`,
              Accept: "application/vnd.github.v3+json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              event_type: "new-capture",
              client_payload: { item_id: data.id },
            }),
          }
        );
      } catch (e) {
        console.error("GitHub dispatch error:", e);
        // Don't fail the request — item is saved, research can be triggered manually
      }
    }

    return NextResponse.json({ ok: true, id: data.id });
  } catch (e) {
    console.error("Capture endpoint error:", e);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
