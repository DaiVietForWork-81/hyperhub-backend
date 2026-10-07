"""
cpp_core package
High-performance C++ Native Acceleration Engine for Discord CP Bot.
"""

from .bridge import (
    IS_NATIVE_ACCELERATED,
    calculate_entropy,
    fast_code_metrics,
    fast_compare_output,
    fast_similarity,
    clean_think_tags,
    dedup_words,
    fast_extract_json,
)

__all__ = [
    "IS_NATIVE_ACCELERATED",
    "calculate_entropy",
    "fast_code_metrics",
    "fast_compare_output",
    "fast_similarity",
    "clean_think_tags",
    "dedup_words",
    "fast_extract_json",
]
