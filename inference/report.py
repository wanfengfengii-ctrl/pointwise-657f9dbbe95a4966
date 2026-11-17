from dataclasses import dataclass
from fractions import Fraction
from inference.contrasts import build_contrast
from inference.unadjusted import UnadjustedResult, compute_unadjusted

UNADJUSTED_WARNING = "未校正选段：普通正态对比仅供人工复核，不是选择后显著性结论。"


@dataclass(frozen=True)
class ReportRequest:
    analysis_id: str
    left_leaf: int


@dataclass(frozen=True)
class ContrastReport:
    analysis_id: str
    revision_id: str
    noise_variance: Fraction
    left_leaf: int
    result: UnadjustedResult
    warning: str


def build_report(request, analysis, revision):
    if analysis.revision_id != revision.revision_id:
        raise ValueError("analysis and data revisions differ")
    vector = build_contrast(analysis.leaves, len(revision.values), request.left_leaf)
    result = compute_unadjusted(vector, revision.values, analysis.request.noise_variance)
    return ContrastReport(request.analysis_id, revision.revision_id,
                          analysis.request.noise_variance, request.left_leaf,
                          result, UNADJUSTED_WARNING)
