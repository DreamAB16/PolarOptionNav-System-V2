"""Vessel-specific enumerations."""

from enum import StrEnum


class IceClass(StrEnum):
    PC1 = "PC1"
    PC2 = "PC2"
    PC3 = "PC3"
    PC4 = "PC4"
    PC5 = "PC5"
    PC6 = "PC6"
    PC7 = "PC7"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


__all__ = ["IceClass"]
