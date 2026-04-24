from __future__ import annotations

import json as _json
import typing as _t

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    """Base for schemas we control end-to-end (events, inputs)."""

    model_config = ConfigDict(extra="forbid")


def _annotation_accepts(ann, target_type: type) -> bool:
    """True if ``ann`` is ``target_type`` or an Optional/Union of it."""
    if ann is target_type:
        return True
    origin = _t.get_origin(ann)
    if origin is _t.Union:
        return any(a is target_type for a in _t.get_args(ann))
    return False


def _stringify(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, dict)):
        try:
            return _json.dumps(v)
        except (TypeError, ValueError):
            return str(v)
    return str(v)


class Lenient(BaseModel):
    """Base for schemas produced by an LLM agent.

    Uses ``extra="ignore"`` so unanticipated fields don't reject real
    agent output. Downstream agents consume these as JSON text blocks,
    not via typed field access, so permissive types are safe.

    A universal ``mode="before"`` model validator walks every declared
    field and coerces scalar type mismatches — stringifies non-strings
    where a ``str`` is expected, wraps scalars in list where a ``list``
    is expected, and replaces non-dict values where a ``dict`` is
    expected with an empty dict. This is the "never reject on scalar
    drift" policy — every agent-emitted type mismatch now becomes a
    best-effort coercion instead of a hard rejection.

    Fields with their own ``field_validator(mode="before")`` are
    SKIPPED by this universal coercion — the per-field validator is
    more specific (e.g. list-of-strings → dict-of-counts for
    ``splits_observed``, flat-dict → list-of-specs for ``splits``)
    and would be pre-empted if we wiped the value first. This is
    load-bearing: without the skip, ``DataEDA.splits_observed``
    emitted as ``["Train", "Validation", "Test"]`` gets wiped to
    ``{}`` before ``_coerce_splits_observed`` can turn it into
    ``{"Train": 0, ...}``.
    """

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _coerce_scalar_mismatches(cls, data):
        if not isinstance(data, dict):
            return data
        # Fields that declare their own ``mode="before"`` field
        # validator know better than the universal coercer. Collect
        # those names so we skip them below.
        before_validated_fields = _collect_before_validated_fields(cls)
        for name, field in cls.model_fields.items():
            if name not in data:
                continue
            v = data[name]
            if v is None:
                continue
            if name in before_validated_fields:
                # Defer to the per-field before-validator. If that
                # validator fails to coerce, pydantic will raise a
                # proper type error; the universal wipe would have
                # silently replaced the value with an empty default.
                continue
            ann = field.annotation
            # str fields: stringify anything non-str.
            if _annotation_accepts(ann, str) and not isinstance(v, str):
                data[name] = _stringify(v)
                continue
            # list-top-level fields (list[X] or Optional[list[X]]):
            # wrap a stray scalar in a list so one drifty entry
            # doesn't reject. Don't touch list-of-X content here —
            # per-field validators handle that.
            origin = _t.get_origin(ann)
            if origin is list and not isinstance(v, list):
                if isinstance(v, (str, int, float, bool)):
                    data[name] = [v]
                elif isinstance(v, dict):
                    data[name] = [v]
                else:
                    data[name] = []
                continue
            # dict-top-level fields (dict[K, V]): replace non-dict
            # with empty dict rather than rejecting.
            if origin is dict and not isinstance(v, dict):
                data[name] = {}
                continue
        return data


def _collect_before_validated_fields(cls: type) -> frozenset[str]:
    """Return the set of field names that declare a ``mode="before"``
    ``field_validator`` on ``cls``.

    Used by ``Lenient._coerce_scalar_mismatches`` to skip its universal
    coercion for fields that have a per-field validator. Caches on
    the class so the decorator walk only runs once per schema.
    """
    cached = getattr(cls, "__before_validated_fields__", None)
    if cached is not None:
        return cached
    names: set[str] = set()
    decorators = getattr(cls, "__pydantic_decorators__", None)
    if decorators is not None:
        for dec in decorators.field_validators.values():
            if getattr(dec.info, "mode", None) == "before":
                names.update(dec.info.fields)
    frozen = frozenset(names)
    try:
        cls.__before_validated_fields__ = frozen
    except (AttributeError, TypeError):
        pass
    return frozen


class CodeSpan(Lenient):
    file_path: str
    # ge=1 sanity cap retained, but before-validators coerce 0 (common
    # agent off-by-one) and negatives to 1 so a drifty line number
    # never rejects a whole findings batch.
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    # Snippet is optional because downstream agents often reference
    # spans by file:line alone without re-quoting the code.
    snippet: str = ""
    context_before: int = Field(default=5, ge=0)
    context_after: int = Field(default=5, ge=0)

    @field_validator("line_start", "line_end", mode="before")
    @classmethod
    def _coerce_line_positive(cls, v):
        if isinstance(v, (int, float)) and v < 1:
            return 1
        return v

    @field_validator("context_before", "context_after", mode="before")
    @classmethod
    def _coerce_context_nonneg(cls, v):
        if isinstance(v, (int, float)) and v < 0:
            return 0
        return v


class Evidence(Lenient):
    # Was a Literal; widened to str because agents produce natural
    # labels like "shell", "python_parse", etc. that weren't in the
    # enumerated set.
    kind: str
    description: str
    raw: str = Field(max_length=4000)

    @field_validator("raw", mode="before")
    @classmethod
    def _truncate_raw(cls, v):
        # Agents sometimes emit long stdout; truncate instead of
        # rejecting the whole finding.
        if isinstance(v, str) and len(v) > 4000:
            return v[:4000]
        if not isinstance(v, str) and v is not None:
            # Agents occasionally emit dict/list in `raw`; stringify.
            return str(v)[:4000]
        return v

    @field_validator("kind", "description", mode="before")
    @classmethod
    def _coerce_nonstr_to_str(cls, v):
        if v is None:
            return ""
        if not isinstance(v, str):
            return str(v)
        return v
