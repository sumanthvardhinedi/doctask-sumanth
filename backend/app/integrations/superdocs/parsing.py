import json
from typing import Any


def parse_proposed_changes(value: Any) -> Any:
    """
    Parse proposed changes returned by SuperDocs.

    Proposed changes arrive as a JSON-encoded string,
    so they require a second JSON parse.
    """
    if isinstance(value, str):
        return json.loads(value)

    return value


def parse_final_result(value: Any) -> Any:
    """
    The final SuperDocs result is already an object.
    """
    return value