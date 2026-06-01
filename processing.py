from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image

InterpolationName = Literal["lanczos4", "cubic", "linear", "area", "nearest"]

INTERPOLATION_MAP: dict[str, int] = {
    "lanczos4": cv2.INTER_LANCZOS4,
    "cubic": cv2.INTER_CUBIC,
    "linear": cv2.INTER_LINEAR,
    "area": cv2.INTER_AREA,
    "nearest": cv2.INTER_NEAREST,
}


@dataclass(frozen=True)
class UpscaleMetadata:
    width: int
    height: int
    original_width: int
    original_height: int
    mode: str
    file_size: int
    has_transparency: bool
    dpi: int
    output_path: str

    def as_dict(self) -> dict[str, int | str | bool]:
        return {
            "width": self.width,
            "height": self.height,
            "original_width": self.original_width,
            "original_height": self.original_height,
            "mode": self.mode,
            "file_size": self.file_size,
            "has_transparency": self.has_transparency,
            "dpi": self.dpi,
            "output_path": self.output_path,
        }


def _load_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("RGBA"), dtype=np.uint8)


def _border_connected_background_mask(
    rgba: np.ndarray,
    threshold: int = 238,
    neutrality_tolerance: int = 7,
) -> np.ndarray:
    rgb = rgba[..., :3]
    max_channel = rgb.max(axis=2)
    min_channel = rgb.min(axis=2)
    candidates = (max_channel >= threshold) & ((max_channel - min_channel) <= neutrality_tolerance)

    candidate_u8 = candidates.astype(np.uint8)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate_u8, connectivity=8)
    if component_count <= 1:
        return np.zeros(candidates.shape, dtype=bool)

    border_labels = np.unique(
        np.concatenate(
            [labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]],
        ),
    )
    border_labels = border_labels[border_labels != 0]
    if border_labels.size == 0:
        return np.zeros(candidates.shape, dtype=bool)

    # Touch stats so OpenCV computes region metadata; labels remain authoritative for border connectivity.
    _ = stats[border_labels]
    return np.isin(labels, border_labels)


def _apply_transparency_cleanup(
    rgba: np.ndarray,
    threshold: int,
    neutrality_tolerance: int,
) -> np.ndarray:
    cleaned = rgba.copy()
    background_mask = _border_connected_background_mask(cleaned, threshold, neutrality_tolerance)
    cleaned[..., 3][background_mask] = 0
    cleaned[..., :3][cleaned[..., 3] == 0] = 0
    return cleaned


def _resize_premultiplied_alpha(
    rgba: np.ndarray,
    width: int,
    height: int,
    interpolation: str = "lanczos4",
) -> np.ndarray:
    interpolation_flag = INTERPOLATION_MAP.get(interpolation, cv2.INTER_LANCZOS4)

    rgba_float = rgba.astype(np.float32) / 255.0
    alpha = rgba_float[..., 3:4]
    premultiplied = rgba_float.copy()
    premultiplied[..., :3] *= alpha

    resized = cv2.resize(premultiplied, (width, height), interpolation=interpolation_flag)
    resized_alpha = resized[..., 3:4]

    unpremultiplied = resized.copy()
    nonzero_alpha = resized_alpha[..., 0] > 1e-6
    unpremultiplied[..., :3][nonzero_alpha] = (
        resized[..., :3][nonzero_alpha] / resized_alpha[nonzero_alpha]
    )
    unpremultiplied[..., :3][~nonzero_alpha] = 0
    unpremultiplied[..., 3:4] = resized_alpha

    output = np.clip(np.rint(unpremultiplied * 255.0), 0, 255).astype(np.uint8)
    output[..., :3][output[..., 3] == 0] = 0
    return output


def _fit_with_transparent_padding(rgba: np.ndarray, width: int, height: int, interpolation: str) -> np.ndarray:
    source_height, source_width = rgba.shape[:2]
    scale = min(width / source_width, height / source_height)
    fitted_width = max(1, int(round(source_width * scale)))
    fitted_height = max(1, int(round(source_height * scale)))
    resized = _resize_premultiplied_alpha(rgba, fitted_width, fitted_height, interpolation)

    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    x = (width - fitted_width) // 2
    y = (height - fitted_height) // 2
    canvas[y : y + fitted_height, x : x + fitted_width] = resized
    return canvas


def _mild_sharpen(rgba: np.ndarray) -> np.ndarray:
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    blurred = cv2.GaussianBlur(rgb, (0, 0), 0.8)
    sharpened = cv2.addWeighted(rgb, 1.15, blurred, -0.15, 0)
    result = rgba.copy()
    result[..., :3] = sharpened
    result[..., :3][alpha == 0] = 0
    return result


def process_image(
    input_path: str | Path,
    output_path: str | Path,
    *,
    width: int = 4500,
    height: int = 5400,
    dpi: int = 300,
    threshold: int = 238,
    neutrality_tolerance: int = 7,
    interpolation: str = "lanczos4",
    compression_level: int = 6,
    keep_aspect_ratio: bool = True,
    transparent_padding: bool = True,
    mild_sharpening: bool = False,
) -> UpscaleMetadata:
    """Run the deterministic preservation-only RGBA upscaling pipeline."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    width = max(1, int(width))
    height = max(1, int(height))
    dpi = max(1, int(dpi))
    threshold = int(np.clip(threshold, 0, 255))
    neutrality_tolerance = int(np.clip(neutrality_tolerance, 0, 255))
    compression_level = int(np.clip(compression_level, 0, 9))

    rgba = _load_rgba(input_path)
    original_height, original_width = rgba.shape[:2]
    rgba = _apply_transparency_cleanup(rgba, threshold, neutrality_tolerance)

    if keep_aspect_ratio and transparent_padding:
        output_rgba = _fit_with_transparent_padding(rgba, width, height, interpolation)
    else:
        if keep_aspect_ratio:
            source_height, source_width = rgba.shape[:2]
            scale = min(width / source_width, height / source_height)
            width = max(1, int(round(source_width * scale)))
            height = max(1, int(round(source_height * scale)))
        output_rgba = _resize_premultiplied_alpha(rgba, width, height, interpolation)

    if mild_sharpening:
        output_rgba = _mild_sharpen(output_rgba)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_image = Image.fromarray(output_rgba, mode="RGBA")
    output_image.save(output_path, format="PNG", dpi=(dpi, dpi), compress_level=compression_level)

    file_size = output_path.stat().st_size
    has_transparency = bool(np.any(output_rgba[..., 3] < 255))
    return UpscaleMetadata(
        width=output_image.width,
        height=output_image.height,
        original_width=original_width,
        original_height=original_height,
        mode=output_image.mode,
        file_size=file_size,
        has_transparency=has_transparency,
        dpi=dpi,
        output_path=str(output_path),
    )
