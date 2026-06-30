from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from .schemas import CandidateProfile


OnMissing = Literal["null", "omit", "error"]


class FieldSpec(BaseModel):
    path: str
    from_: Optional[str] = Field(default=None, alias="from")
    type: str
    required: bool = False
    normalize: Optional[str] = None


class ProjectionConfig(BaseModel):
    fields: List[FieldSpec]
    include_provenance: bool = False
    include_confidence: bool = False
    on_missing: OnMissing = "null"


def _resolve_simple_path(data: Any, path: str) -> Any:
    """
    Resolve a very small JSONPath-like expression against a dict/list structure.
    Supports:
      - a.b
      - a[0]
      - a[].b  (returns list of b values)
    """
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if not part:
            return None

        if part.endswith("[]"):
            key = part[:-2]
            current = current.get(key) if isinstance(current, dict) else None
            if not isinstance(current, list):
                return []
        elif "[" in part and part.endswith("]"):
            key, index_str = part[:-1].split("[", 1)
            current = current.get(key) if isinstance(current, dict) else None
            if not isinstance(current, list):
                return None
            try:
                idx = int(index_str)
            except ValueError:
                return None
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
        else:
            current = current.get(part) if isinstance(current, dict) else None

        if current is None:
            return None
    return current


def _resolve_path(data: Any, path: str) -> Any:
    """
    Extended resolver that understands a leading list-collect segment like
    'skills[].name' by applying _resolve_simple_path element-wise.
    """
    if "[]" not in path:
        return _resolve_simple_path(data, path)

    prefix, rest = path.split("[]", 1)
    prefix = prefix.rstrip(".")
    rest = rest.lstrip(".")

    root_list = _resolve_simple_path(data, prefix)
    if not isinstance(root_list, list):
        return []

    if not rest:
        return root_list

    results = []
    for item in root_list:
        value = _resolve_simple_path(item, rest)
        if value is not None:
            results.append(value)
    return results


def _apply_normalizer(name: Optional[str], value: Any) -> Any:
    # For now we only support identity normalizers; hook exists for extension.
    if name is None:
        return value
    # "E164" and "canonical" can be treated as pass-through because canonical
    # profile is already normalized by the merge layer.
    return value


def validate_config_for_profile(config: ProjectionConfig) -> None:
    # Very lightweight validation: ensure the first segment of every path/from
    # refers to a real CandidateProfile field.
    valid_roots = set(CandidateProfile.model_fields.keys())
    for field in config.fields:
        raw_path = field.from_ or field.path
        root = raw_path.split(".", 1)[0]
        root = root.split("[", 1)[0].rstrip("[]")
        if root not in valid_roots:
            raise ValueError(f"Config references unknown root field '{root}'")


def project_profile(profile: CandidateProfile, config: ProjectionConfig) -> Dict[str, Any]:
    """
    Apply a ProjectionConfig to a canonical CandidateProfile, returning a
    plain dict suitable for JSON response.
    """
    try:
        validate_config_for_profile(config)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    data = profile.model_dump()
    output: Dict[str, Any] = {}

    for field in config.fields:
        target_key = field.path
        source_path = field.from_ or field.path

        value = _resolve_path(data, source_path)

        if value is None:
            if config.on_missing == "error" or field.required:
                raise ValueError(f"Missing required field '{target_key}' from path '{source_path}'")
            if config.on_missing == "null":
                output[target_key] = None
            # on_missing == "omit" -> skip key entirely
            continue

        value = _apply_normalizer(field.normalize, value)

        # Simple type enforcement for string vs string[].
        if field.type == "string" and isinstance(value, list):
            value = value[0] if value else None
        elif field.type == "string[]" and not isinstance(value, list):
            value = [value]

        output[target_key] = value

    return output

