from dataclasses import fields, is_dataclass
from fractions import Fraction
import hashlib
import json
import math
from sampling.types import SampleRow, ImportPayload, SeriesRevision
from sampling.validation import normalize_import, identity
from selection.request import AnalysisRequest, validate_request
from selection.statistics import SegmentStatistics
from selection.partition import LeafSpan, apply_split, initial_partition, validate_partition
from selection.greedy import SplitStep, AnalysisResult
from inference.contrasts import ContrastVector
from inference.normal import NormalSummary
from inference.unadjusted import UnadjustedResult
from inference.report import ContrastReport, UNADJUSTED_WARNING
from archive.schema import FixedTask, ArtifactEnvelope, CorruptArtifact

_TYPES = {kind.__name__: kind for kind in (
    SampleRow, ImportPayload, SeriesRevision, AnalysisRequest, SegmentStatistics,
    SplitStep, AnalysisResult, ContrastVector, NormalSummary, UnadjustedResult,
    ContrastReport, FixedTask, ArtifactEnvelope)}


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def artifact_digest(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _pack(value):
    if isinstance(value, Fraction):
        return {"$fraction": [value.numerator, value.denominator]}
    if is_dataclass(value) and type(value).__name__ in _TYPES:
        return {"$type": type(value).__name__,
                "fields": {field.name: _pack(getattr(value, field.name))
                           for field in fields(value)}}
    if isinstance(value, tuple):
        return {"$tuple": [_pack(item) for item in value]}
    if value is None or type(value) in (str, int, float):
        if type(value) is float and not math.isfinite(value):
            raise ValueError("nonfinite encoded number")
        return value
    raise ValueError("unsupported encoded value")


def _unpack(value):
    if value is None or type(value) in (str, int, float):
        if type(value) is float and not math.isfinite(value):
            raise ValueError("nonfinite number")
        return value
    if not isinstance(value, dict):
        raise ValueError("unknown wire structure")
    if set(value) == {"$fraction"}:
        pair = value["$fraction"]
        if (not isinstance(pair, list) or len(pair) != 2 or
                any(type(item) is not int for item in pair) or pair[1] <= 0):
            raise ValueError("invalid fraction")
        result = Fraction(*pair)
        if [result.numerator, result.denominator] != pair:
            raise ValueError("fraction is not canonical")
        return result
    if set(value) == {"$tuple"} and isinstance(value["$tuple"], list):
        return tuple(_unpack(item) for item in value["$tuple"])
    if set(value) == {"$type", "fields"} and value["$type"] in _TYPES:
        kind = _TYPES[value["$type"]]
        body = value["fields"]
        if not isinstance(body, dict) or set(body) != {field.name for field in fields(kind)}:
            raise ValueError("encoded fields differ from type schema")
        result = kind(**{key: _unpack(item) for key, item in body.items()})
        _validate(result)
        return result
    raise ValueError("unknown encoded tag")


def _fraction(value):
    if type(value) is not Fraction:
        raise ValueError("expected an exact fraction")


def _integer(value, lower=0):
    if type(value) is not int or value < lower:
        raise ValueError("invalid integer")


def _validate(value):
    if isinstance(value, SampleRow):
        _integer(value.row_no)
        _fraction(value.value)
    elif isinstance(value, ImportPayload):
        if type(value.rows) is not tuple or any(type(row) is not SampleRow for row in value.rows):
            raise ValueError("invalid rows")
        normalized = normalize_import(value.series_id, value.source_version, value.unit,
                                      value.rows, value.correction_parent)
        if normalized != value:
            raise ValueError("noncanonical import")
    elif isinstance(value, SeriesRevision):
        identity(value.revision_id, "revision_id")
        if type(value.payload) is not ImportPayload:
            raise ValueError("invalid revision payload")
    elif isinstance(value, AnalysisRequest):
        _fraction(value.noise_variance)
        if validate_request(value.noise_variance, value.min_leaf, value.splits) != value:
            raise ValueError("invalid request")
    elif isinstance(value, SegmentStatistics):
        _integer(value.l)
        _integer(value.r, value.l + 1)
        _integer(value.count, 1)
        for item in (value.total, value.sum_squares, value.mean, value.sse):
            _fraction(item)
        if (value.count != value.r - value.l or value.mean != value.total / value.count or
                value.sse != value.sum_squares - value.total ** 2 / value.count or
                value.sse < 0 or value.sum_squares < 0):
            raise ValueError("invalid segment statistics")
    elif isinstance(value, SplitStep):
        _integer(value.l)
        _integer(value.c, value.l + 1)
        _integer(value.r, value.c + 1)
        _fraction(value.gain)
        if value.gain < 0:
            raise ValueError("negative gain")
    elif isinstance(value, AnalysisResult):
        identity(value.revision_id, "revision_id")
        if (type(value.request) is not AnalysisRequest or type(value.steps) is not tuple or
                type(value.leaves) is not tuple or not value.leaves or
                any(type(item) is not SplitStep for item in value.steps) or
                any(type(item) is not SegmentStatistics for item in value.leaves) or
                len(value.steps) != value.request.splits):
            raise ValueError("invalid analysis")
        n = value.leaves[-1].r
        leaves = initial_partition(n, value.request.min_leaf)
        for step in value.steps:
            leaves = apply_split(leaves, step.l, step.c, step.r, value.request.min_leaf)
        actual = tuple(LeafSpan(leaf.l, leaf.r) for leaf in value.leaves)
        validate_partition(actual, n, value.request.min_leaf)
        if actual != leaves:
            raise ValueError("steps and final partition differ")
    elif isinstance(value, ContrastVector):
        _integer(value.left_leaf)
        if type(value.coefficients) is not tuple or not value.coefficients:
            raise ValueError("empty contrast")
        for coefficient in value.coefficients:
            _fraction(coefficient)
        if sum(value.coefficients, Fraction(0)) != 0 or not any(value.coefficients):
            raise ValueError("invalid mean contrast")
    elif isinstance(value, NormalSummary):
        _fraction(value.variance)
        if (value.variance <= 0 or not isinstance(value.standard_error, str) or
                type(value.p) is not float or not math.isfinite(value.p) or not 0 <= value.p <= 1):
            raise ValueError("invalid normal summary")
        from decimal import Decimal
        se = Decimal(value.standard_error)
        if not se.is_finite() or se <= 0:
            raise ValueError("invalid standard error")
    elif isinstance(value, UnadjustedResult):
        if type(value.vector) is not ContrastVector or type(value.normal) is not NormalSummary:
            raise ValueError("invalid ordinary result")
        _fraction(value.z)
        _fraction(value.norm_squared)
        if value.norm_squared != sum((c*c for c in value.vector.coefficients), Fraction(0)):
            raise ValueError("coefficient norm mismatch")
    elif isinstance(value, ContrastReport):
        identity(value.analysis_id, "analysis_id")
        identity(value.revision_id, "revision_id")
        _fraction(value.noise_variance)
        _integer(value.left_leaf)
        if (type(value.result) is not UnadjustedResult or value.noise_variance <= 0 or
                value.left_leaf != value.result.vector.left_leaf or
                value.result.normal.variance != value.noise_variance * value.result.norm_squared or
                value.warning != UNADJUSTED_WARNING):
            raise ValueError("invalid ordinary report")
    elif isinstance(value, FixedTask):
        identity(value.task_id, "task_id")
        identity(value.revision_id, "revision_id")
        if type(value.request) is not AnalysisRequest:
            raise ValueError("invalid task parameters")
    elif isinstance(value, ArtifactEnvelope):
        identity(value.artifact_id, "artifact_id")
        identity(value.parent_id, "parent_id")
        expected = {"analysis": AnalysisResult, "report": ContrastReport}
        if value.kind not in expected or type(value.data) is not expected[value.kind]:
            raise ValueError("invalid artifact kind")
        if value.kind == "report" and value.parent_id != value.data.analysis_id:
            raise ValueError("report parent mismatch")


def _encode(value, kind):
    if type(value) is not kind:
        raise ValueError("wrong encoding type")
    _validate(value)
    body = canonical_json({"version": 1, "object": _pack(value)})
    _decode(body, kind)
    return body


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode(body, kind):
    try:
        raw = json.loads(body, object_pairs_hook=_unique_pairs,
                         parse_constant=lambda text: (_ for _ in ()).throw(ValueError(text)))
        if not isinstance(raw, dict) or set(raw) != {"version", "object"}:
            raise ValueError("invalid envelope")
        if type(raw["version"]) is not int or raw["version"] != 1:
            raise ValueError("unsupported encoding version")
        result = _unpack(raw["object"])
        if type(result) is not kind:
            raise ValueError("unexpected top-level object type")
        return result
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError) as exc:
        raise CorruptArtifact("invalid versioned object: " + str(exc)) from exc


def encode_import_payload(value):
    return _encode(value, ImportPayload)


def encode_revision(value):
    return _encode(value, SeriesRevision)


def decode_revision(body):
    return _decode(body, SeriesRevision)


def encode_task(value):
    return _encode(value, FixedTask)


def decode_task(body):
    return _decode(body, FixedTask)


def encode_artifact(value):
    return _encode(value, ArtifactEnvelope)


def decode_artifact(body):
    return _decode(body, ArtifactEnvelope)
