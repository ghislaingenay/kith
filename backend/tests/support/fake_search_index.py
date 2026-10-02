"""An in-memory `SearchIndex` stand-in that records whether the index and
alias were created."""


class FakeSearchIndex:
    def __init__(self, *, index_exists: bool = False) -> None:
        self.index_exists = index_exists
        self.ensure_calls = 0

    @property
    def alias(self) -> str:
        return "kith-chunks"

    async def ensure_index(self) -> None:
        self.ensure_calls += 1
        self.index_exists = True

    async def alias_exists(self) -> bool:
        return self.index_exists

    async def close(self) -> None:
        pass
