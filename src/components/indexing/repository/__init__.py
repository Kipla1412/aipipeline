"""Chunk repository package — persistence backends for clinical chunks."""

from .opensearch import OpenSearchRepository

__all__ = ["OpenSearchRepository"]
