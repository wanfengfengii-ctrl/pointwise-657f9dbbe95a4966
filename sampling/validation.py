from fractions import Fraction
from sampling.types import SampleRow, ImportPayload


def normalize_rational(value):
    if isinstance(value, bool) or not isinstance(value, (int, Fraction, str)):
        raise ValueError("expected an integer, Fraction or rational string")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("invalid rational value") from exc


def identity(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " must be a nonempty string")
    return value


def validate_rows(rows):
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("a nonempty ordered row array is required")
    result = []
    for index, row in enumerate(rows):
        if isinstance(row, SampleRow):
            number, value = row.row_no, row.value
        elif isinstance(row, dict) and set(row) == {"row_no", "value"}:
            number, value = row["row_no"], row["value"]
        else:
            raise ValueError("each row requires row_no and value")
        if type(number) is not int or number != index:
            raise ValueError("row_no must match its zero-based array position")
        result.append(SampleRow(number, normalize_rational(value)))
    return tuple(result)


def normalize_import(series_id, source_version, unit, rows, correction_parent=None):
    identity(series_id, "series_id")
    identity(source_version, "source_version")
    if unit != "mg/L":
        raise ValueError("only mg/L is accepted")
    if correction_parent is not None:
        identity(correction_parent, "correction_parent")
    return ImportPayload(series_id, source_version, unit, validate_rows(rows),
                         correction_parent)
