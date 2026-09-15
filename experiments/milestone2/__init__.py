"""Milestone 2 SIFT1M benchmark infrastructure.

The package is intentionally separate from the immutable Milestone 1 smoke
pipeline.  Qualification profiles are bounded to at most 100,000 rows.
"""

from .metrics import canonical_recall_at_k, tie_aware_recall_at_k

__all__ = ["canonical_recall_at_k", "tie_aware_recall_at_k"]
