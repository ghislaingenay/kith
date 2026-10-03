"""Abstract interface the search store implements."""

from abc import ABC, abstractmethod


class SearchIndex(ABC):
    """The one place the application talks to the keyword and vector search
    store (ADR-0012)."""

    @property
    @abstractmethod
    def alias(self) -> str:
        """The alias the application reads and writes through."""

    @abstractmethod
    async def ensure_index(self) -> None:
        """Create the versioned index and its alias if they do not exist.
        Calling it again changes nothing."""

    @abstractmethod
    async def alias_exists(self) -> bool:
        """Whether the alias exists, without creating anything."""

    @abstractmethod
    async def close(self) -> None:
        """Release the client's connections."""
