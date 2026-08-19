"""
SpacePoint - IDW Heat Surface Interpolation
Author: Kommal
"""

import base64
import io

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np


def compute_idw_grid(points: np.ndarray, values: np.ndarray, bounds: tuple,
                      grid_size: int = 100, power: int = 2, k_neighbors: int = 10):
    """Inverse Distance Weighting restricted to each grid cell's k
    nearest readings, so local clusters stay visible instead of
    blurring into the whole dataset's average.

    points: array of (lat, lon) pairs. values: matching sensor readings.
    bounds: (min_lat, max_lat, min_lon, max_lon).
    """
    min_lat, max_lat, min_lon, max_lon = bounds
    lat_grid = np.linspace(min_lat, max_lat, grid_size)
    lon_grid = np.linspace(min_lon, max_lon, grid_size)
    lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)

    grid_points = np.stack([lat_mesh.ravel(), lon_mesh.ravel()], axis=1)  # (G, 2)
    diffs = grid_points[:, None, :] - points[None, :, :]                  # (G, N, 2)
    distances = np.sqrt((diffs ** 2).sum(axis=2))                        # (G, N)
    distances = np.where(distances == 0, 1e-10, distances)

    k = min(k_neighbors, points.shape[0])
    nearest_idx = np.argsort(distances, axis=1)[:, :k]           # (G, k)
    row_idx = np.arange(distances.shape[0])[:, None]
    nearest_distances = distances[row_idx, nearest_idx]          # (G, k)
    nearest_values = values[nearest_idx]                         # (G, k)

    weights = 1 / (nearest_distances ** power)
    interpolated = (weights * nearest_values).sum(axis=1) / weights.sum(axis=1)

    return interpolated.reshape(grid_size, grid_size)


def render_heat_overlay_png(grid: np.ndarray) -> str:
    """Renders the grid as a transparent, padding-free PNG so its pixel
    edges line up exactly with the data bounds for Leaflet's imageOverlay."""
    colors = ["#3E5872", "#4FD1C5", "#F5C97A"]  # matches DATA_RAMP in branding.py
    cmap = mcolors.LinearSegmentedColormap.from_list("spacepoint_heat", colors)

    fig = plt.figure(figsize=(6, 6), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1])  # no margins
    ax.axis("off")
    ax.imshow(grid, cmap=cmap, origin="lower", aspect="auto", interpolation="bilinear")

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", transparent=True)
    plt.close(fig)
    buffer.seek(0)

    encoded = base64.b64encode(buffer.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"