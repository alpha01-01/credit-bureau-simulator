"""Seeded random streams (Document 07, Section 5.3).

Every random draw comes from a stream identified by (world seed, stream name,
optional step). Streams are independent, so adding draws to one stream never
shifts the numbers in another, and any step can be regenerated on its own.
"""

from __future__ import annotations

import hashlib

import numpy as np


def _name_key(name: str) -> int:
    # Stable across processes and platforms (unlike hash()).
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "little")


def stream(seed: int, name: str, step: int = 0) -> np.random.Generator:
    """Return an independent generator for (seed, name, step)."""
    entropy = [seed & 0xFFFFFFFFFFFFFFFF, _name_key(name), step]
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy)))
