"""Paper-claim schemas.

These are consumed by downstream agents as inline JSON text blocks, not
via typed field access — so we use a permissive `Lenient` base that
accepts extra fields and loose types. An idealized taxonomy can't
anticipate every field an LLM will produce when reading a real paper.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import Field, field_validator

from .common import Lenient


class Citation(Lenient):
    page: Optional[int] = None
    section: Optional[str] = None
    quote: str = Field(max_length=500)

    @field_validator("quote", mode="before")
    @classmethod
    def _truncate_quote(cls, v):
        if isinstance(v, str) and len(v) > 500:
            return v[:500]
        return v


class MetricClaim(Lenient):
    id: str
    metric_name: Optional[str] = None
    value: Optional[Union[float, str]] = None
    unit: Optional[str] = "percent"
    stddev: Optional[float] = None
    n_seeds: Optional[int] = None
    dataset: Optional[str] = None
    split: str = "test"
    condition: Optional[str] = None
    citation: Optional[Citation] = None


class DatasetSplitSpec(Lenient):
    name: Optional[str] = None
    num_samples: Optional[int] = None
    num_classes: Optional[int] = None


class DatasetClaim(Lenient):
    id: str
    name: Optional[str] = None
    num_samples_total: Optional[int] = None
    splits: list[DatasetSplitSpec] = Field(default_factory=list)
    modality: list[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    license: Optional[str] = None
    citation: Optional[Citation] = None

    @field_validator("modality", mode="before")
    @classmethod
    def _coerce_modality(cls, v):
        if isinstance(v, str):
            return [v]
        if v is None:
            return []
        return v

    @field_validator("splits", mode="before")
    @classmethod
    def _coerce_splits(cls, v):
        """Agents commonly emit ``splits: ["train", "val"]`` as bare
        strings instead of DatasetSplitSpec objects. Coerce each bare
        string into ``{"name": s}`` so the schema still validates."""
        if v is None:
            return []
        if isinstance(v, dict):
            # Agents sometimes emit splits as a dict keyed by split name.
            # Coerce {"train": 50000, "val": 5000} → list of specs.
            out = []
            for k, val in v.items():
                if isinstance(val, dict):
                    spec = {"name": k, **val}
                elif isinstance(val, int):
                    spec = {"name": k, "num_samples": val}
                else:
                    spec = {"name": k}
                out.append(spec)
            return out
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, str):
                    out.append({"name": item})
                else:
                    out.append(item)
            return out
        return v


class ArchitectureClaim(Lenient):
    id: str
    component: Optional[str] = None
    architecture: Optional[str] = None
    parameter_count: Optional[int] = None
    frozen: Optional[bool] = None
    citation: Optional[Citation] = None


class TrainingConfigClaim(Lenient):
    id: str
    optimizer: Optional[str] = None
    learning_rate: Optional[float] = None
    learning_rate_schedule: Optional[str] = None
    batch_size: Optional[int] = None
    epochs: Optional[int] = None
    weight_decay: Optional[float] = None
    momentum: Optional[float] = None
    loss_function: Optional[str] = None
    seed: Optional[int] = None
    mixed_precision: Optional[bool] = None
    gradient_clipping: Optional[float] = None
    notes: Optional[str] = None
    citation: Optional[Citation] = None


class EvaluationProtocolClaim(Lenient):
    id: str
    metrics: list[str] = Field(default_factory=list)
    split: str = "test"
    test_time_augmentation: Optional[bool] = None
    noise_conditions: list[str] = Field(default_factory=list)
    post_processing: Optional[str] = None
    # Was ``dict[str, str]``; widened to ``Any`` because agents
    # sometimes emit nested structures here (variant→{threshold, etc}).
    metric_variants: dict[str, Any] = Field(default_factory=dict)
    citation: Optional[Citation] = None


class AblationClaim(Lenient):
    id: str
    description: Optional[str] = None
    baseline_metric: Optional[MetricClaim] = None
    ablated_metric: Optional[MetricClaim] = None
    citation: Optional[Citation] = None


class PaperRedFlag(Lenient):
    category: Optional[str] = None
    description: Optional[str] = None
    citation: Optional[Citation] = None


class PaperClaims(Lenient):
    paper_title: str
    authors: list[str]
    arxiv_id: Optional[str] = None
    year: Optional[int] = None
    abstract_summary: str = Field(max_length=3000)

    @field_validator("abstract_summary", mode="before")
    @classmethod
    def _truncate_abstract(cls, v):
        if isinstance(v, str) and len(v) > 3000:
            return v[:3000]
        return v

    @field_validator("extraction_confidence", mode="before")
    @classmethod
    def _clamp_extraction_confidence(cls, v):
        if v is None:
            return 0.5
        if isinstance(v, (int, float)):
            if v < 0:
                return 0.0
            if v > 1:
                return 1.0
        return v
    metrics: list[MetricClaim] = Field(default_factory=list)
    datasets: list[DatasetClaim] = Field(default_factory=list)
    architectures: list[ArchitectureClaim] = Field(default_factory=list)
    training_config: list[TrainingConfigClaim] = Field(default_factory=list)
    evaluation_protocol: list[EvaluationProtocolClaim] = Field(
        default_factory=list
    )
    ablations: list[AblationClaim] = Field(default_factory=list)
    red_flags: list[PaperRedFlag] = Field(default_factory=list)
    extraction_confidence: float = Field(ge=0, le=1)
    unresolved_questions: list[str] = Field(default_factory=list)
