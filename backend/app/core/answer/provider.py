"""Abstract interface the answer model implements (ADR-0016)."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class AnswerRequest:
    instructions: str
    """What the model is told to do, apart from the data it works on."""
    prompt: str
    """The Query and the numbered passages, in delimited data blocks."""


class AnswerEnding(StrEnum):
    COMPLETED = "completed"
    CUT_OFF = "cut_off"
    """The model hit the output cap before it finished."""
    FAILED = "failed"


@dataclass(frozen=True)
class AnswerUsage:
    """Token counts as the provider reported them."""

    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    """Already included in `output_tokens`."""


@dataclass(frozen=True)
class AnswerDelta:
    text: str


@dataclass(frozen=True)
class AnswerEnd:
    ending: AnswerEnding
    usage: AnswerUsage | None
    """`None` when the provider reported none."""


class AnswerProvider(ABC):
    @abstractmethod
    def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerEnd]:
        """Streams the Answer's text deltas, then exactly one `AnswerEnd`. A
        response the model itself failed ends with `AnswerEnding.FAILED`; a
        model that cannot be reached raises `AnswerUnavailableError`, and a
        rejected request raises `AnswerError`."""
