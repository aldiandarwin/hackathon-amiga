"""Offline AMIGA invoice processing prototype. No network or billing calls."""

from .pipeline import process_invoice

__all__ = ["process_invoice"]
