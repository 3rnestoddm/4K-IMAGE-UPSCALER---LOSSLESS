# 4K Image Upscaler — Deterministic Preservation Preview

This app is a local-first FastAPI tool for previewing deterministic 4K upscaling before publishing or committing results anywhere.

> **Important:** no raster upscaler can create new original image information. This project is “lossless” in the preservation-workflow sense: it avoids OCR, AI generation, redraw, face restoration, and text reconstruction, uses deterministic resampling, preserves transparency, and exports a PNG you can inspect locally.

## Local preview workflow

1. Install the dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

2. Start the local server:

   ```bash
   uvicorn app:app --reload
   ```

3. Open the app in your browser:

   ```text
   http://127.0.0.1:8000
   ```

4. Drag in a PNG, JPG, or WEBP and click **Upscale 4500 x 5400**.
5. Confirm the on-page metadata says the output is `4500 × 5400` pixels.
6. Click **Open Preview** to inspect the processed transparent PNG in a browser tab before you download, publish, or commit it.
7. Click **Download PNG** only after the preview looks correct.

## What the app does

- Loads uploads with Pillow and converts them to RGBA.
- Detects bright neutral fake-background/checkerboard candidates.
- Keeps only candidate regions connected to the image border with OpenCV connected components.
- Makes those border-connected background pixels transparent.
- Resizes with premultiplied alpha using OpenCV `INTER_LANCZOS4` by default.
- Saves a transparent PNG with 300 DPI metadata by default.

## Safety defaults

- Files stay local in `uploads/` and `outputs/`.
- Filenames are generated from UUIDs and never overwrite existing user files.
- Upload extensions are limited to PNG, JPG/JPEG, and WEBP.
- Upload size is bounded by `MAX_UPLOAD_SIZE` and defaults to 25 MiB.
