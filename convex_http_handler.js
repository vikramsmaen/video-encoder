import { httpRouter } from "convex/server";
import { httpAction } from "./_generated/server";
import { internal } from "./_generated/api";

const http = httpRouter();

http.route({
    path: "/populateVideo",
    method: "POST",
    handler: httpAction(async (ctx, request) => {
        // 1️⃣ Verify secret from HEADER (best practice)
        const secret = request.headers.get("x-webhook-secret");
        if (secret !== process.env.CONVEX_WEBHOOK_SECRET) {
            return new Response("Unauthorized", { status: 401 });
        }

        // 2️⃣ Parse body
        const body = await request.json();
        const { r2MasterPath, folderName, duration, thumbnailUrl } = body;

        if (!r2MasterPath || !folderName) {
            return new Response("Missing required fields", { status: 400 });
        }

        // 3️⃣ Clean title safely
        const title = folderName
            .replace(/_/g, " ")
            .replace(/\s+/g, " ")
            .trim();

        // 4️⃣ Insert via internal mutation
        await ctx.runMutation(internal.videos.insertVideo, {
            title,
            r2MasterPath,
            duration: duration ?? 0,
            thumbnailUrl: thumbnailUrl ?? "",
            isPremium: true
        });

        return new Response(
            JSON.stringify({ success: true }),
            { status: 200, headers: { "Content-Type": "application/json" } }
        );
    }),
});

export default http;
