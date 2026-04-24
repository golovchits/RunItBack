from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import Field, field_validator

from .common import CodeSpan, Evidence, Lenient


class FindingCategory(str, Enum):
    # Data leakage (code-side)
    DATA_LEAKAGE_PREPROCESSING = "data_leakage.preprocessing"
    DATA_LEAKAGE_OVERLAP = "data_leakage.overlap"
    DATA_LEAKAGE_MULTITEST = "data_leakage.multi_test"
    DATA_LEAKAGE_TEMPORAL = "data_leakage.temporal"
    DATA_LEAKAGE_TARGET = "data_leakage.target"
    # Environment
    ENV_HARDCODED_PATH = "environment.hardcoded_path"
    ENV_MISSING_PIN = "environment.missing_version_pin"
    ENV_UNRESOLVED_IMPORT = "environment.unresolved_import"
    ENV_NOTEBOOK_FRAGILITY = "environment.notebook_fragility"
    # Data loader
    DATA_LOADER_MEMORY_BLOAT = "dataloader.memory_bloat"
    DATA_LOADER_INDEX_MISMATCH = "dataloader.index_mismatch"
    DATA_LOADER_SHUFFLE_DECOUPLE = "dataloader.shuffle_decouple"
    # Preprocessing
    PREPROC_AUGMENTATION_LEAK = "preprocessing.augmentation_leak_into_eval"
    PREPROC_INTERPOLATION_MISMATCH = "preprocessing.interpolation_mismatch"
    PREPROC_SINGLE_TRANSFORM = "preprocessing.single_shared_transform"
    PREPROC_FLAG_SWAPPED = "preprocessing.flag_swapped"
    # Architecture
    ARCH_BROADCASTING = "architecture.silent_broadcasting"
    ARCH_OMITTED_STATE = "architecture.omitted_state_tensor"
    ARCH_COMPILER_GRAPH_BREAK = "architecture.compiler_graph_break"
    # API / defaults
    API_DEFAULT_DRIFT = "api.default_value_drift"
    # Determinism / seeding
    DETERMINISM_MISSING_SEEDS = "determinism.missing_seeds"
    DETERMINISM_CUDNN_NONDET = "determinism.cudnn_nondeterministic"
    DETERMINISM_WORKER_SEED = "determinism.worker_seed_not_offset"
    # State / mode
    MODE_EVAL_NOT_TOGGLED = "state.eval_mode_not_toggled"
    CHECKPOINT_INCOMPLETE = "state.checkpoint_incomplete"
    # Distributed training
    DISTRIBUTED_SAMPLER_EPOCH = "distributed.sampler_epoch_not_updated"
    DISTRIBUTED_DROPOUT_MIRROR = "distributed.dropout_mask_unsynced"
    # Evaluation
    EVAL_METRIC_IMPL_MISMATCH = "eval.metric_implementation_mismatch"
    EVAL_POSTPROCESS_MISMATCH = "eval.post_processing_mismatch"
    EVAL_SPLIT_USED_INCORRECTLY = "eval.split_used_incorrectly"
    # Config / training
    CONFIG_VS_PAPER_MISMATCH = "config.value_mismatch_with_paper"
    FROZEN_BACKBONE_CLAIM_MISMATCH = "training.frozen_backbone_claim_mismatch"
    DEAD_CODE_INTENDED_BEHAVIOR_MISSING = "code_quality.dead_code_intended_behavior_missing"
    # Data-side
    DATA_CORRUPT_FILES = "data.corrupt_or_zero_byte_files"
    DATA_MISSING_SEQUENCE = "data.missing_sequence_gap"
    DATA_SPLIT_REFERENCES_MISSING = "data.split_file_references_missing"
    DATA_COUNT_VS_CLAIM_MISMATCH = "data.sample_count_mismatch_with_paper"
    DATA_CLASS_DIST_MISMATCH = "data.class_distribution_mismatch"
    DATA_DUPLICATES_ACROSS_SPLITS = "data.duplicates_across_splits"
    DATA_FORMAT_INCONSISTENCY = "data.format_inconsistency"
    DATA_ORPHAN_ANNOTATIONS = "data.orphan_annotations_or_files"
    DATA_CHECKPOINT_CORRUPT = "data.checkpoint_corrupt_or_wrong_shape"
    DATA_CHECKPOINT_NAN = "data.checkpoint_values_nan_or_zero"
    DATA_LABEL_COMPLETENESS = "data.labels_missing_for_samples"
    DATA_METADATA_MISMATCH = "data.metadata_does_not_match_directory"
    # Meta
    OTHER = "other"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class DetectorRole(str, Enum):
    AUDITOR = "auditor"
    VALIDATOR = "validator"
    REVIEWER = "reviewer"


class DataEDA(Lenient):
    splits_observed: dict[str, int] = Field(default_factory=dict)
    class_distribution: dict[str, dict[str, int]] = Field(default_factory=dict)
    file_format_stats: dict[str, int] = Field(default_factory=dict)
    sample_dimensions_summary: Optional[str] = None
    corrupt_files: list[str] = Field(default_factory=list)
    duplicate_hashes: list[list[str]] = Field(default_factory=list)

    @field_validator("splits_observed", mode="before")
    @classmethod
    def _coerce_splits_observed(cls, v):
        """Agents often emit ``splits_observed: ["train", "val"]`` (a
        list of split names they noticed) instead of the
        dict[name, count] shape. Coerce both the list form and None
        into a dict so validation doesn't reject an otherwise-valid
        EDA block. When count is unknown we use 0 as a placeholder."""
        if v is None:
            return {}
        if isinstance(v, list):
            return {str(item): 0 for item in v}
        if isinstance(v, dict):
            out = {}
            for k, val in v.items():
                if isinstance(val, int):
                    out[str(k)] = val
                elif isinstance(val, float):
                    out[str(k)] = int(val)
                elif isinstance(val, str):
                    try:
                        out[str(k)] = int(val.strip())
                    except (ValueError, AttributeError):
                        out[str(k)] = 0
                else:
                    out[str(k)] = 0
            return out
        return v

    @field_validator("class_distribution", mode="before")
    @classmethod
    def _coerce_class_distribution(cls, v):
        # Expects dict[split, dict[class, count]]. Agents sometimes
        # flatten to dict[class, count] or emit counts as strings.
        if v is None:
            return {}
        if not isinstance(v, dict):
            return {}
        out = {}
        for split, inner in v.items():
            if not isinstance(inner, dict):
                # flattened or unrecognized → wrap under a synthetic split
                continue
            coerced_inner = {}
            for cls_name, count in inner.items():
                try:
                    coerced_inner[str(cls_name)] = int(count)
                except (TypeError, ValueError):
                    coerced_inner[str(cls_name)] = 0
            out[str(split)] = coerced_inner
        return out

    @field_validator("file_format_stats", mode="before")
    @classmethod
    def _coerce_file_format_stats(cls, v):
        if v is None:
            return {}
        if isinstance(v, list):
            return {str(item): 0 for item in v}
        if isinstance(v, dict):
            out = {}
            for k, val in v.items():
                try:
                    out[str(k)] = int(val)
                except (TypeError, ValueError):
                    out[str(k)] = 0
            return out
        return v

    @field_validator("duplicate_hashes", mode="before")
    @classmethod
    def _coerce_duplicate_hashes(cls, v):
        # Schema is ``list[list[str]]`` — pairs/groups of colliding
        # filenames. Agents frequently drift to:
        #   - a plain summary string ("172 MD5 collisions found")
        #   - a list of dicts with `note` keys
        #   - a single flat list of strings (one group, not grouped)
        # Coerce all of these into a shape the schema will accept so
        # a summary-style emission doesn't kill the whole EDA block.
        if v is None:
            return []
        if isinstance(v, str):
            return [[v]]
        if isinstance(v, dict):
            note = v.get("note") or v.get("summary") or str(v)
            return [[str(note)]]
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, list):
                    out.append([str(x) for x in item])
                elif isinstance(item, str):
                    out.append([item])
                elif isinstance(item, dict):
                    note = item.get("note") or item.get("summary") or str(item)
                    out.append([str(note)])
                else:
                    out.append([str(item)])
            return out
        return v

    @field_validator("corrupt_files", mode="before")
    @classmethod
    def _coerce_corrupt_files(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v]
        return v


class AuditFinding(Lenient):
    id: str
    category: FindingCategory
    severity: Severity
    title: str = Field(max_length=160)
    description: str
    paper_claim_refs: list[str] = Field(default_factory=list)

    code_span: Optional[CodeSpan] = None
    data_path: Optional[str] = None

    evidence: list[Evidence] = Field(default_factory=list)

    paper_says: Optional[str] = None
    code_does: Optional[str] = None

    suggested_fix_diff: Optional[str] = None
    suggested_fix_prose: Optional[str] = None

    confidence: float = Field(ge=0, le=1)
    detector: DetectorRole
    cross_refs: list[str] = Field(default_factory=list)

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, v):
        # Map agent-emitted category strings that aren't in our taxonomy
        # to OTHER so a single novel category doesn't reject the whole
        # findings batch.
        if isinstance(v, FindingCategory):
            return v
        if isinstance(v, str):
            for member in FindingCategory:
                if member.value == v:
                    return v
            return FindingCategory.OTHER.value
        return v

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v):
        # Agents emit "warn", "Low", "urgent", etc. that aren't in the
        # enum. Normalize casing first, then map unknown values to
        # "info" so one novel severity doesn't reject the batch.
        if isinstance(v, Severity):
            return v
        if isinstance(v, str):
            lowered = v.strip().lower()
            for member in Severity:
                if member.value == lowered:
                    return lowered
            if lowered in {"warn", "warning"}:
                return Severity.MEDIUM.value
            if lowered in {"urgent", "blocker"}:
                return Severity.CRITICAL.value
            return Severity.INFO.value
        return v

    @field_validator("title", mode="before")
    @classmethod
    def _truncate_title(cls, v):
        if isinstance(v, str) and len(v) > 160:
            return v[:160]
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v):
        if v is None:
            return 0.5
        if isinstance(v, (int, float)):
            if v < 0:
                return 0.0
            if v > 1:
                return 1.0
        return v

    @field_validator("evidence", mode="before")
    @classmethod
    def _normalize_evidence(cls, v):
        # Evidence schema requires {kind, description, raw}. Agents
        # frequently emit {path, line, content} or {file, snippet}
        # or just a bare string. Coerce all of these into the
        # required shape so one drifty evidence entry doesn't
        # reject the whole finding.
        if v is None:
            return []
        if isinstance(v, str):
            return [{"kind": "note", "description": v[:160], "raw": v}]
        if not isinstance(v, list):
            return []
        out = []
        for item in v:
            if isinstance(item, str):
                out.append({"kind": "note",
                            "description": item[:160],
                            "raw": item})
                continue
            if not isinstance(item, dict):
                out.append({"kind": "note", "description": str(item)[:160],
                            "raw": str(item)})
                continue
            # Field-rename drift: {path, line, content/snippet}
            if "kind" not in item:
                if "type" in item:
                    item["kind"] = item.pop("type")
                else:
                    item["kind"] = "code" if item.get("path") else "note"
            if "description" not in item:
                path = item.get("path") or item.get("file")
                line = item.get("line") or item.get("line_start")
                if path and line:
                    item["description"] = f"{path}:{line}"
                elif path:
                    item["description"] = str(path)
                else:
                    item["description"] = item.get("summary") or item.get(
                        "kind", "evidence"
                    )
            if "raw" not in item:
                raw = (
                    item.get("content")
                    or item.get("snippet")
                    or item.get("text")
                    or item.get("output")
                )
                item["raw"] = str(raw) if raw is not None else ""
            out.append(item)
        return out


class TargetedCheckRequest(Lenient):
    finding_id: str
    hypothesis: str
    proposed_check: str
    priority: Literal["high", "medium", "low"]

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, v):
        # Agents drift to "urgent", "critical", "normal", "low-medium".
        # Coerce to the closest valid bucket so one drifty request
        # doesn't reject the whole findings batch.
        if isinstance(v, str):
            lowered = v.strip().lower()
            if lowered in {"high", "medium", "low"}:
                return lowered
            if lowered in {"critical", "urgent", "p0", "p1"}:
                return "high"
            if lowered in {"normal", "moderate", "default"}:
                return "medium"
            return "medium"
        return v


class AuditFindings(Lenient):
    findings: list[AuditFinding]
    repo_summary: str = Field(max_length=3000)
    data_summary: Optional[str] = Field(default=None, max_length=3000)
    eda: Optional[DataEDA] = None
    coverage_notes: list[str] = Field(default_factory=list)
    targeted_check_requests: list[TargetedCheckRequest] = Field(default_factory=list)

    @field_validator("repo_summary", "data_summary", mode="before")
    @classmethod
    def _truncate_summary(cls, v):
        # Auditor tours a repo in detail and sometimes writes a tour
        # longer than 3000 chars. Truncate instead of rejecting so
        # nothing important gets lost to a hard cap.
        if isinstance(v, str) and len(v) > 3000:
            return v[:3000]
        return v
