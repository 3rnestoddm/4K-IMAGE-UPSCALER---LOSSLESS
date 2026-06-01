from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from processing import INTERPOLATION_MAP, process_image

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(25 * 1024 * 1024)))

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Deterministic Preservation Upscaler")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _safe_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed}")
    return extension


def _unique_path(directory: Path, suffix: str) -> Path:
    for _ in range(20):
        candidate = directory / f"{uuid4().hex}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=500, detail="Could not allocate a unique filename")


def _bounded_int(value: int, minimum: int, maximum: int, field_name: str) -> int:
    if value < minimum or value > maximum:
        raise HTTPException(status_code=400, detail=f"{field_name} must be between {minimum} and {maximum}")
    return value


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "preservation-only"}


@app.post("/upscale")
def upscale(
    file: UploadFile = File(...),
    width: int = Form(4500),
    height: int = Form(5400),
    dpi: int = Form(300),
    threshold: int = Form(238),
    neutrality_tolerance: int = Form(7),
    interpolation: str = Form("lanczos4"),
    compression_level: int = Form(6),
    keep_aspect_ratio: bool = Form(True),
    transparent_padding: bool = Form(True),
    mild_sharpening: bool = Form(False),
) -> dict[str, object]:
    extension = _safe_extension(file.filename or "")
    width = _bounded_int(width, 1, 12000, "width")
    height = _bounded_int(height, 1, 12000, "height")
    dpi = _bounded_int(dpi, 1, 1200, "dpi")
    threshold = _bounded_int(threshold, 0, 255, "threshold")
    neutrality_tolerance = _bounded_int(neutrality_tolerance, 0, 255, "neutrality_tolerance")
    compression_level = _bounded_int(compression_level, 0, 9, "compression_level")
    if interpolation not in INTERPOLATION_MAP:
        raise HTTPException(status_code=400, detail="Unsupported interpolation method")

    upload_path = _unique_path(UPLOAD_DIR, extension)
    output_path = _unique_path(OUTPUT_DIR, ".png")

    bytes_written = 0
    try:
        with upload_path.open("wb") as destination:
            while chunk := file.file.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="Upload exceeds configured maximum size")
                destination.write(chunk)

        metadata = process_image(
            upload_path,
            output_path,
            width=width,
            height=height,
            dpi=dpi,
            threshold=threshold,
            neutrality_tolerance=neutrality_tolerance,
            interpolation=interpolation,
            compression_level=compression_level,
            keep_aspect_ratio=keep_aspect_ratio,
            transparent_padding=transparent_padding,
            mild_sharpening=mild_sharpening,
        )
    except HTTPException:
        upload_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not process image: {exc}") from exc
    finally:
        file.file.close()

    file_id = output_path.stem
    return {
        "file_id": file_id,
        "preview_url": f"/preview/{file_id}",
        "download_url": f"/download/{file_id}",
        "metadata": metadata.as_dict(),
        "preservation_mode": {
            "ocr": False,
            "ai_generation": False,
            "redraw": False,
            "face_restoration": False,
            "text_reconstruction": False,
        },
    }


def _output_path_for_file_id(file_id: str) -> Path:
    if not file_id or any(character not in "0123456789abcdef" for character in file_id) or len(file_id) != 32:
        raise HTTPException(status_code=404, detail="File not found")

    output_path = OUTPUT_DIR / f"{file_id}.png"
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return output_path


@app.get("/preview/{file_id}")
def preview(file_id: str) -> FileResponse:
    output_path = _output_path_for_file_id(file_id)
    return FileResponse(
        output_path,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="preview-{file_id}.png"'},
    )


@app.get("/download/{file_id}")
def download(file_id: str) -> FileResponse:
    output_path = _output_path_for_file_id(file_id)
    return FileResponse(
        output_path,
        media_type="image/png",
        filename=f"upscaled-{file_id}.png",
    )
