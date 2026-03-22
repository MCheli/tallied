from datetime import date, datetime

from app.parsers.base import BaseParser, ParseResult


class GenericParser(BaseParser):
    """Fallback parser that wraps raw data minimally.

    Used for unknown sources or screenshot captures that need
    manual review or future Claude vision processing.
    """

    def can_handle(self, source: str) -> bool:
        # Generic parser is the fallback — it can handle anything
        return True

    def parse(self, raw_data: dict | str) -> ParseResult:
        if isinstance(raw_data, str):
            import json

            try:
                raw_data = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError):
                # Not JSON — treat as opaque text payload
                return ParseResult(
                    records=[],
                    summary={
                        "type": "raw_text",
                        "length": len(raw_data),
                        "needs_review": True,
                    },
                    errors=[],
                )

        data_type = raw_data.get("type", "unknown") if isinstance(raw_data, dict) else "unknown"

        # For screenshot or image captures, flag for vision processing
        is_screenshot = data_type in ("screenshot", "image", "photo")

        summary: dict = {
            "type": data_type,
            "needs_review": True,
            "needs_vision": is_screenshot,
        }

        if isinstance(raw_data, dict):
            summary["keys"] = list(raw_data.keys())

        return ParseResult(
            records=[],
            summary=summary,
            errors=[],
        )
