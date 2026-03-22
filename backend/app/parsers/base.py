from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParseResult:
    """Result from parsing raw data."""

    records: list[dict] = field(default_factory=list)  # List of records with a "table" key and data
    summary: dict = field(default_factory=dict)  # Summary for import_log.parsed_summary
    errors: list[str] = field(default_factory=list)  # Any non-fatal parsing errors


class BaseParser(ABC):
    @abstractmethod
    def parse(self, raw_data: dict | str) -> ParseResult:
        """Parse raw captured data into structured records."""
        ...

    @abstractmethod
    def can_handle(self, source: str) -> bool:
        """Whether this parser handles the given source."""
        ...
