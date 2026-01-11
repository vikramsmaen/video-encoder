import { httpRouter } from "convex/server";
import { httpAction } from "./_generated/server";
import { internal } from "./_generated/api";

const http = httpRouter();

http.route({
  path: "/populateVideo",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const { r2MasterPath, folderName, duration, assets, secret } = await request.json();

    // 1. Verify Secret
    if (secret !== process.env.CONVEX_WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    // 2. Call Internal Mutation
    // We assume 'internal.videos.saveVideoData' exists as per comment above.
    // If the video doesn't exist yet, you might want to call 'insertVideo' first or handle it in 'saveVideoData'.

    await ctx.runMutation(internal.videos.saveVideoData, {
      r2MasterPath,
      duration: duration || 0,
      assets: assets || []
    });

    return new Response("Success", { status: 200 });
  }),
});

export default http;



/*
  >>> SCHEMA UPDATE REQUIRED <<<
  Add the following table to your convex/schema.ts:

  video_data: defineTable({
    videoId: v.id("videos"),
    type: v.string(), // "thumbnail", "preview_clip", "progression_sprite"
    url: v.string(),
    index: v.number(), // 1, 2, 3...
  }).index("by_videoId", ["videoId"]),

  Add the 'saveVideoData' mutation to convex/videos.ts (or similar):

  export const saveVideoData = internalMutation({
    args: {
      r2MasterPath: v.string(),
      duration: v.number(),
      assets: v.array(v.object({
        type: v.string(),
        url: v.string(),
        index: v.number()
      }))
    },
    handler: async (ctx, args) => {
      // 1. Find Video
      const video = await ctx.db
        .query("videos")
        .withIndex("by_r2MasterPath", (q) => q.eq("r2MasterPath", args.r2MasterPath))
        .first();

      if (!video) {
        console.error("Video not found for assets:", args.r2MasterPath);
        return; // Or create incomplete record
      }

      // 2. Update Video Duration
      await ctx.db.patch(video._id, { duration: args.duration });

      // 3. Insert Assets into 'video_data' table
      // Optional: Clear old assets for this video to avoid duplicates if re-uploaded
      const oldAssets = await ctx.db
        .query("video_data")
        .withIndex("by_videoId", (q) => q.eq("videoId", video._id))
        .collect();
      
      for (const asset of oldAssets) {
        await ctx.db.delete(asset._id);
      }

      // Insert new
      for (const asset of args.assets) {
        await ctx.db.insert("video_data", {
          videoId: video._id,
          type: asset.type,
          url: asset.url,
          index: asset.index,
        });
      }
    },
  });
*/
