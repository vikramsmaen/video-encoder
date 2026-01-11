# Adaptive Quality (AQ) Video Encoding Guide

**Target**: Build a Python application that converts a single video into **adaptive-quality HLS output**, ready for **Cloudflare R2** storage and **Next.js playback**.

This document is written so you can **paste it directly into Cursor / AI IDE** and start coding step-by-step.

---

## 0. AQ STANDARD (DEFINE ONCE)

### Resolution & Bitrate Ladder

```
240p  → 426x240  → 400 kbps
360p  → 640x360  → 800 kbps
480p  → 854x480  → 1400 kbps
720p  → 1280x720 → 2800 kbps
```

Rules:

* Skip 1080p unless absolutely required
* 240p–720p is optimal for cost vs quality

---

## 1. INPUT VALIDATION (PYTHON STEP)

Before encoding, validate the input video.

### Checks

* File exists
* Duration > 5 seconds
* Video stream exists
* Resolution >= highest target (720p)

### Extract Metadata (ffprobe)

```bash
ffprobe -v error -select_streams v:0 \
-show_entries stream=width,height,r_frame_rate \
-of json input.mp4
```

Python responsibilities:

* Parse width, height, FPS
* Decide which resolutions are allowed
* Store FPS for GOP calculation

---

## 2. OUTPUT DIRECTORY STRUCTURE (STRICT)

Your Python app must create the following structure **exactly**:

```
output/
  video_id/
    master.m3u8
    240p.m3u8
    360p.m3u8
    480p.m3u8
    720p.m3u8
    segments/
      240p_000.ts
      360p_000.ts
      480p_000.ts
      720p_000.ts
```

Python example:

```python
os.makedirs("output/video_id/segments", exist_ok=True)
```

---

## 3. NORMALIZE INPUT (OPTIONAL BUT RECOMMENDED)

Normalize audio and enable fast start.

```bash
ffmpeg -i input.mp4 \
-c:v copy \
-c:a aac -ar 48000 \
-movflags faststart \
normalized.mp4
```

Why:

* Prevents audio inconsistencies
* Faster first-frame playback

---

## 4. AQ HLS ENCODING (CORE STEP)

### Single-Pass Multi-Resolution HLS Encode

```bash
ffmpeg -i normalized.mp4 \
-filter_complex \
"[0:v]split=4[v1][v2][v3][v4]; \
[v1]scale=426:240[v240]; \
[v2]scale=640:360[v360]; \
[v3]scale=854:480[v480]; \
[v4]scale=1280:720[v720]" \
-map "[v240]" -map 0:a -c:v:0 libx264 -b:v:0 400k \
-map "[v360]" -map 0:a -c:v:1 libx264 -b:v:1 800k \
-map "[v480]" -map 0:a -c:v:2 libx264 -b:v:2 1400k \
-map "[v720]" -map 0:a -c:v:3 libx264 -b:v:3 2800k \
-c:a aac -ac 2 -ar 48000 \
-preset medium \
-profile:v main \
-g 48 -keyint_min 48 \
-f hls \
-hls_time 6 \
-hls_playlist_type vod \
-hls_segment_filename "output/video_id/segments/%v_%03d.ts" \
-master_pl_name master.m3u8 \
-var_stream_map "v:0,a:0 v:1,a:0 v:2,a:0 v:3,a:0" \
output/video_id/%v.m3u8
```

---

## 5. NAMING CONVENTION RULES (MANDATORY)

| Asset             | Rule                      |
| ----------------- | ------------------------- |
| Master playlist   | `master.m3u8`             |
| Variant playlists | `{resolution}.m3u8`       |
| Segments          | `{resolution}_{index}.ts` |

Do not deviate. This ensures:

* Player compatibility
* CDN caching efficiency
* Easy cleanup

---

## 6. OUTPUT VALIDATION (AUTOMATED)

Your Python app must verify:

* `master.m3u8` exists
* All resolution playlists exist
* Segment count > 0
* Playlist paths are valid

Optional:

```bash
ffprobe output/video_id/master.m3u8
```

---

## 7. UPLOAD TO CLOUDFLARE R2

Upload the **entire video folder**.

### Final R2 Structure

```
r2-bucket/
  videos/
    video_id/
      master.m3u8
      240p.m3u8
      360p.m3u8
      480p.m3u8
      720p.m3u8
      segments/
```

### Content-Type Rules

| File    | Content-Type                    |
| ------- | ------------------------------- |
| `.m3u8` | `application/vnd.apple.mpegurl` |
| `.ts`   | `video/mp2t`                    |

Use **S3-compatible SDK** (boto3).

---

## 8. CLEANUP (COST CONTROL)

After successful upload:

* Delete original upload
* Delete normalized file
* Keep only encoded HLS output

---

## 9. PLAYBACK FLOW (REFERENCE)

```
User clicks play
 → Backend generates signed URL (master.m3u8)
 → Next.js loads HLS via hls.js
 → Video streams from R2 via CDN
```

Never expose raw R2 URLs publicly.

---

## 10. FAILURE HANDLING STRATEGY

Your AQ service should:

* Retry encoding once
* Capture FFmpeg logs
* Mark video as `failed_encoding`
* Continue processing next job

Never block the queue.

---

## 11. SCALING STRATEGY (FUTURE)

* One encode job per CPU core
* Queue-based processing (Redis / Convex / SQS)
* GPU encoding only if volume is very high

---

## FINAL AQ PIPELINE SUMMARY

```
Upload Video
   ↓
Validate Metadata
   ↓
Normalize Input
   ↓
AQ HLS Encode
   ↓
Verify Output
   ↓
Upload to R2
   ↓
Cleanup
   ↓
Ready for Streaming
```

---

## NEXT FILES YOU MAY WANT

* `python-aq-encoder.py` (starter skeleton)
* `r2-upload-helper.py`
* `signed-url-generator.md`
* `cloudflare-worker-stream.md`
* `encoding-cost-calculator.md`

This document is intentionally **implementation-ready** for AI-assisted coding.
