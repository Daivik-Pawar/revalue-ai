"""Shared lookup tables: relative part tiers and storage sizes.

Tiers are rough, self-defined 1-5 orderings of parts (1 = entry, 5 = high end).
They are NOT benchmark scores. The dataset generator and the Flask app both
import this file, so training rows and live predictions use identical values.
"""
import re

CPU_TIER = {
    "Intel Core i3-1215U": 1.8, "Intel Core i5-1235U": 2.6, "Intel Core i7-1255U": 3.2,
    "Intel Core i5-11400H": 3.0, "Intel Core i7-11800H": 3.8,
    "Intel Core i5-12450H": 3.4, "Intel Core i7-12650H": 4.2,
    "AMD Ryzen 5 5600H": 3.2, "AMD Ryzen 7 7435HS": 4.0, "AMD Ryzen 5 8645HS": 4.4,
    "Apple M1 (8-core CPU, 7-core GPU)": 3.6, "Apple M1 (8-core CPU, 8-core GPU)": 3.8,
    "Apple M2 (8-core CPU, 8-core GPU)": 4.2, "Apple M2 (8-core CPU, 10-core GPU)": 4.4,
}
DGPU_TIER = {
    "NVIDIA GeForce GTX 1650": 1.5, "NVIDIA GeForce RTX 2050": 1.8,
    "NVIDIA GeForce RTX 3050": 2.5, "NVIDIA GeForce RTX 3050 Ti": 2.8,
    "NVIDIA GeForce RTX 3060": 3.3, "NVIDIA GeForce RTX 3070": 4.0,
    "NVIDIA GeForce RTX 4050": 3.2, "NVIDIA GeForce RTX 4060": 3.8,
    "NVIDIA GeForce RTX 4070": 4.5, "AMD Radeon RX 6500M": 1.6,
}
STORAGE_GB = {"120 GB": 120, "128 GB": 128, "240 GB": 240, "256 GB": 256, "480 GB": 480, "500 GB": 500,
              "512 GB": 512, "960 GB": 960, "1 TB": 1000, "2 TB": 2000, "4 TB": 4000, "8 TB": 8000}

# name: (illustrative new price in rupees, tier)
CPU_ANCHOR = {"Intel Core i5-12400F": (13000, 3.0), "Intel Core i5-13400F": (19000, 3.4), "Intel Core i7-12700K": (30000, 4.0),
              "AMD Ryzen 5 5600": (12000, 2.8), "AMD Ryzen 5 5600X": (15000, 3.0), "AMD Ryzen 7 5800X": (24000, 3.8),
              "AMD Ryzen 5 7600": (21000, 3.6), "AMD Ryzen 7 7700X": (30000, 4.2)}
GPU_ANCHOR = {"NVIDIA GeForce GTX 1650": (14000, 1.5), "NVIDIA GeForce GTX 1660 Super": (19000, 2.2),
              "NVIDIA GeForce RTX 3050": (25000, 2.5), "NVIDIA GeForce RTX 3060": (33000, 3.3),
              "NVIDIA GeForce RTX 4060": (30000, 3.8), "NVIDIA GeForce RTX 4060 Ti": (42000, 4.2),
              "AMD Radeon RX 580": (15000, 1.7), "AMD Radeon RX 6600": (23000, 3.0)}

_CPU_TEXT_TIERS = [  # (regex, tier). Order matters: first match wins.
    (r"celeron|pentium|athlon", 1.0),
    (r"i3|ryzen\s*3", 1.8),
    (r"i5|ryzen\s*5", 3.0),
    (r"i7|ryzen\s*7", 3.8),
    (r"i9|ryzen\s*9|threadripper", 4.5),
]


def _words(s):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split())


def cpu_tier_from_text(text):
    """Tier for a typed CPU name: exact known name first, then a family heuristic.

    Returns None when nothing matches, so the caller treats it as unknown.
    """
    if not text:
        return None
    known = {**CPU_TIER, **{k: v[1] for k, v in CPU_ANCHOR.items()}}
    for name, tier in known.items():
        if name.lower() == str(text).strip().lower():
            return tier
    t = str(text).lower()
    for pattern, tier in _CPU_TEXT_TIERS:
        if re.search(pattern, t):
            return tier
    return None


def gpu_tier_from_text(text):
    """Tier for a typed GPU name by matching known model tokens (e.g. 'rtx 3060').

    The longest matching token wins, so 'rtx 3050 ti' beats 'rtx 3050'.
    Returns None for cards not in the known list (treated as unknown).
    """
    if not text:
        return None
    words = _words(text)
    table = {**DGPU_TIER, **{k: v[1] for k, v in GPU_ANCHOR.items()}}
    best = None
    for name, tier in table.items():
        token = _words(name).replace("nvidia geforce ", "").replace("amd radeon ", "")
        if f" {token} " in f" {words} " and (best is None or len(token) > best[0]):
            best = (len(token), tier)
    return best[1] if best else None
