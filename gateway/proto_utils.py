"""
Shared protobuf → dict conversion for the gateway subscribers.

Centralizes the MessageToDict options so the wire contract lives in ONE place:
  * preserving_proto_field_name=True       — snake_case keys matching the proto
  * always_print_fields_with_no_presence=True
        — presence-less scalar/enum fields (e.g. `source`) are ALWAYS emitted.
          This is the protobuf>=5.x spelling; the old `including_default_value_fields`
          kwarg was removed in protobuf 5.x and raises TypeError on 5.27.2 (pinned),
          which previously broke the entire event/prediction fan-out.

Keeping this in one helper means a future protobuf bump only needs a single edit,
and `gateway/tests/unit/test_proto_utils.py` pins the behavior against regressions.

Owner: Samad
"""

from __future__ import annotations

from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message


def to_dict(message: Message) -> dict[str, Any]:
    """Convert a protobuf message to a JSON-serializable dict for the browser."""
    return MessageToDict(
        message,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=True,
    )
