"""Small interface for source-specific adapters into environment fields."""

from abc import ABC, abstractmethod

from core.environment import EnvironmentField, FieldMetadata


class BaseProviderAdapter(ABC):
    """Translate one external dataset into the shared environment contract."""

    @abstractmethod
    def load(self) -> None:
        """Open or prepare the adapter's external dataset."""

    @abstractmethod
    def read_metadata(self) -> FieldMetadata:
        """Read source facts and express them using shared field metadata."""

    @abstractmethod
    def convert_to_environment_field(self) -> EnvironmentField:
        """Convert source values into a generic EnvironmentField."""
