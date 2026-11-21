import json

from pydantic import ValidationError

from aq.config import OUTPUT_DIR, REJECTED_PATH, log
from aq.models import Record


def validate_records(raw_records: list[dict], run_at: str = "") -> tuple[list[Record], int]:
    """Return valid records. Invalid ones are written to rejected_records.jsonl."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    valid: list[Record] = []
    rejected = 0
    with open(REJECTED_PATH, "a", encoding="utf-8") as bad_file:
        for raw in raw_records:
            try:
                valid.append(Record.model_validate(raw))
            except ValidationError as exc:
                rejected += 1
                bad_file.write(
                    json.dumps(
                        {"run_at": run_at, "errors": exc.errors(include_url=False), "raw": raw},
                        default=str,
                    )
                    + "\n"
                )
    log.info("Validation: %d valid, %d rejected", len(valid), rejected)
    return valid, rejected
