from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class SampleRow:
    row_no: int
    value: Fraction


@dataclass(frozen=True)
class ImportPayload:
    series_id: str
    source_version: str
    unit: str
    rows: tuple[SampleRow, ...]
    correction_parent: str | None = None


@dataclass(frozen=True)
class SeriesRevision:
    revision_id: str
    payload: ImportPayload

    @property
    def values(self):
        return tuple(row.value for row in self.payload.rows)
