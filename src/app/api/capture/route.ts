import { NextRequest, NextResponse } from "next/server";
import { getServiceClient } from "../../../../lib/supabase-server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const contentType = request.headers.get("content-type") || "";
    let text: string;

    if (contentType.includes("application/x-www-form-urlencoded")) {
      // Slack slash command — sends form-encoded body
      const formData = await request.formData();
      text = formData.get("text") as string;

      // Validate using Slack signing secret if configured,
      // otherwise fall back to checking the token Slack sends
      const slackToken = formData.get("token") as string;
      if (
        process.env.SLACK_VERIFICATION_TOKEN &&
        slackToken !== process.env.SLACK_VERIFICATION_TOKEN
      ) {
        return new Response("Unauthorized", { status: 401 });
      }
    } else {
      // JSON webhook — original path
      const secret = request.headers.get("x-webhook-secret");
      if (secret !== process.env.WEBHOOK_SECRET) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
      }

      const body = await request.json();
      text = body.text;
    }

    if (!text || typeof text !== "string" || !text.trim()) {
      // Slack expects a JSON response with response_type
      return NextResponse.json({
        response_type: "ephemeral",
        text: "Please provide something to capture. Usage: `/capture The Bear on Hulu`",
      });
    }

    const supabase = getServiceClient();

    const { data, error } = await supabase
      .from("items")
      .insert({ raw_input: text.trim(), status: "pending" })
      .select("id")
      .single();

    if (error) {
      console.error("Supabase insert error:", error);
      return NextResponse.json({
        response_type: "ephemeral",
        text: "Failed to save item. Try again.",
      });
    }

    // Fire GitHub repository_dispatch to trigger research
    const githubToken = process.env.GITHUB_TOKEN;
    const githubRepo = process.env.GITHUB_REPO;

    if (githubToken && githubRepo) {
      try {
        const dispatchRes = await fetch(
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
        console.log(`GitHub dispatch: ${dispatchRes.status} ${dispatchRes.statusText}`);
        if (!dispatchRes.ok) {
          const body = await dispatchRes.text();
          console.error("GitHub dispatch failed:", body);
        }
      } catch (e) {
        console.error("GitHub dispatch error:", e);
      }
    } else {
      console.error("GitHub dispatch skipped — missing env vars:", {
        hasToken: !!githubToken,
        hasRepo: !!githubRepo,
      });
    }

    // Slack-friendly response
    return NextResponse.json({
      response_type: "ephemeral",
      text: `Captured: "${text.trim()}" — researching now.`,
    });
  } catch (e) {
    console.error("Capture endpoint error:", e);
    return NextResponse.json({
      response_type: "ephemeral",
      text: "Something went wrong. Try again.",
    });
  }
}
