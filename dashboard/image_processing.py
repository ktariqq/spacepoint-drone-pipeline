"""
SpacePoint - Drone Image Processing (Computer Vision Pipeline)
Author: Kommal
"""

import cv2
import numpy as np
from PIL import Image

MAX_WIDTH = 800
LAND_COVER_CLUSTERS = 6

# ExG's real range for 8-bit RGB is -510 to 510. ExG <= 0 means no real
# greenness, regardless of how a pixel compares to the rest of its image.
EXG_PHYSICAL_RANGE = (-510, 510)
MIN_VEGETATION_EXG = 0.0

# Brightness (RMS of R,G,B) is naturally 0-255. Below this floor, a
# pixel isn't a bright/bare surface no matter its image-relative rank.
BRIGHTNESS_PHYSICAL_RANGE = (0, 255)
MIN_BRIGHT_SURFACE_VALUE = 140.0


def load_image(file) -> Image.Image:
    image = Image.open(file)
    return image.convert("RGB")


def resize_image(image: Image.Image, max_width: int = MAX_WIDTH) -> Image.Image:
    if image.width <= max_width:
        return image
    ratio = max_width / image.width
    new_size = (max_width, int(image.height * ratio))
    return image.resize(new_size)


def denoise(image_array: np.ndarray) -> np.ndarray:
    """Light blur before index calculation so noise can't shift Otsu's cutoff."""
    return cv2.GaussianBlur(image_array, (5, 5), 0)


def compute_vegetation_index(image_array: np.ndarray) -> np.ndarray:
    """Excess Green Index (ExG = 2G - R - B), on its real physical scale."""
    image_float = image_array.astype(float)
    red, green, blue = image_float[:, :, 0], image_float[:, :, 1], image_float[:, :, 2]
    return 2 * green - red - blue


def compute_brightness_index(image_array: np.ndarray) -> np.ndarray:
    """Surface brightness index (RMS of R, G, B)."""
    image_float = image_array.astype(float)
    red, green, blue = image_float[:, :, 0], image_float[:, :, 1], image_float[:, :, 2]
    return np.sqrt((red**2 + green**2 + blue**2) / 3)


def scale_to_uint8(raw_array: np.ndarray, physical_range: tuple) -> np.ndarray:
    """Maps a raw index to 0-255 on a fixed physical range shared across
    all images, not each image's own min/max."""
    lo, hi = physical_range
    clipped = np.clip(raw_array, lo, hi)
    return ((clipped - lo) / (hi - lo) * 255).astype(np.uint8)


def normalize_for_display(raw_array: np.ndarray, physical_range: tuple) -> np.ndarray:
    """Same fixed-scale mapping, returned as 0-1 floats for overlay opacity."""
    lo, hi = physical_range
    return np.clip((raw_array - lo) / (hi - lo), 0, 1)


def otsu_threshold(raw_index: np.ndarray, physical_range: tuple, absolute_floor: float) -> tuple[np.ndarray, float]:
    """Otsu's adaptive cutoff on the fixed physical scale, combined with
    an absolute floor - Otsu can raise the bar but never invent a
    detection where the raw index shows none. Returns mask + raw cutoff."""
    index_uint8 = scale_to_uint8(raw_index, physical_range)
    otsu_cutoff_uint8, _ = cv2.threshold(index_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    lo, hi = physical_range
    otsu_cutoff_raw = lo + (otsu_cutoff_uint8 / 255) * (hi - lo)
    effective_cutoff = max(otsu_cutoff_raw, absolute_floor)

    mask = raw_index > effective_cutoff
    return mask, effective_cutoff


def classify_cluster_color(center: np.ndarray) -> str:
    """Labels one K-means cluster center by color, using HSV so hue tells
    apart categories that look similar in brightness alone - asphalt
    (gray, low saturation) vs. bare soil (brown) vs. water (blue hue)."""
    r, g, b = center
    hsv_pixel = cv2.cvtColor(np.uint8([[[r, g, b]]]), cv2.COLOR_RGB2HSV)[0][0]
    hue, sat, val = int(hsv_pixel[0]), int(hsv_pixel[1]), int(hsv_pixel[2])

    if val < 60:
        return "shadow"
    if g > r and g > b and sat > 40:
        return "vegetation"
    if 95 <= hue <= 135 and b >= r and sat > 30:
        return "water"
    if 5 <= hue <= 30 and sat > 45 and val < 200:
        return "bare_soil"
    if sat < 35 and val >= 170:
        return "bright_surface"
    if sat < 40 and val < 170:
        return "asphalt_pavement"
    return "other"


def classify_land_cover(image_array: np.ndarray, k: int = LAND_COVER_CLUSTERS) -> dict:
    """Unsupervised K-means clustering on pixel colors, labeled by each
    cluster's average color."""
    pixels = image_array.reshape(-1, 3).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS)

    label_map = labels.flatten().reshape(image_array.shape[:2])
    cluster_names = {cluster_id: classify_cluster_color(center) for cluster_id, center in enumerate(centers)}

    return {"label_map": label_map, "cluster_names": cluster_names}


def compute_coverage_stats(vegetation_mask, brightness_mask, land_cover) -> dict:
    total_pixels = vegetation_mask.size

    stats = {
        "vegetation_pct": round(float(vegetation_mask.sum()) / total_pixels * 100, 1),
        "bright_surface_pct": round(float(brightness_mask.sum()) / total_pixels * 100, 1),
    }

    label_map = land_cover["label_map"]
    category_totals = {}
    for cluster_id, name in land_cover["cluster_names"].items():
        pct = round(float((label_map == cluster_id).sum()) / total_pixels * 100, 1)
        category_totals[name] = category_totals.get(name, 0) + pct
    stats["land_cover_breakdown"] = category_totals

    return stats


def create_annotated_image(image_array, vegetation_index, brightness_index, vegetation_mask, brightness_mask) -> Image.Image:
    """Translucent overlay whose strength scales with each pixel's index
    value - purple for vegetation, red for bright/hot surfaces."""
    overlay = image_array.astype(float).copy()

    purple = np.array([155, 93, 229])
    red = np.array([214, 60, 60])

    veg_display = normalize_for_display(vegetation_index, EXG_PHYSICAL_RANGE)
    bright_display = normalize_for_display(brightness_index, BRIGHTNESS_PHYSICAL_RANGE)

    veg_alpha = veg_display * 0.5 + 0.15
    bright_alpha = bright_display * 0.5 + 0.15

    for c in range(3):
        channel = overlay[:, :, c]
        channel[vegetation_mask] = channel[vegetation_mask] * (1 - veg_alpha[vegetation_mask]) + purple[c] * veg_alpha[vegetation_mask]
        channel[brightness_mask] = channel[brightness_mask] * (1 - bright_alpha[brightness_mask]) + red[c] * bright_alpha[brightness_mask]
        overlay[:, :, c] = channel

    return Image.fromarray(np.clip(overlay, 0, 255).astype("uint8"))


def analyze_image(file) -> dict:
    """Runs the full CV pipeline on one image."""
    original = load_image(file)
    resized = resize_image(original)
    image_array = np.array(resized)
    denoised = denoise(image_array)

    vegetation_index = compute_vegetation_index(denoised)
    brightness_index = compute_brightness_index(denoised)

    vegetation_mask, veg_cutoff = otsu_threshold(vegetation_index, EXG_PHYSICAL_RANGE, MIN_VEGETATION_EXG)
    brightness_mask, bright_cutoff = otsu_threshold(brightness_index, BRIGHTNESS_PHYSICAL_RANGE, MIN_BRIGHT_SURFACE_VALUE)
    brightness_mask = brightness_mask & (~vegetation_mask)

    land_cover = classify_land_cover(denoised)
    stats = compute_coverage_stats(vegetation_mask, brightness_mask, land_cover)
    stats["vegetation_threshold"] = round(float(veg_cutoff), 1)
    stats["brightness_threshold"] = round(float(bright_cutoff), 1)

    annotated = create_annotated_image(image_array, vegetation_index, brightness_index, vegetation_mask, brightness_mask)

    return {"original": resized, "annotated": annotated, "stats": stats}