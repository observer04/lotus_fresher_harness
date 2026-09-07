from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


class OpenAPIValidationError(ValueError):
    pass


def _basic_checks(spec: dict[str, Any]) -> None:
    if not isinstance(spec, dict):
        raise OpenAPIValidationError("OpenAPI document must be a mapping")
    version = str(spec.get("openapi", ""))
    if not version.startswith("3."):
        raise OpenAPIValidationError("Only OpenAPI 3.x documents are supported")
    if not isinstance(spec.get("info"), dict):
        raise OpenAPIValidationError("Missing info object")
    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise OpenAPIValidationError("OpenAPI document must contain paths")
    seen: set[str] = set()
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            raise OpenAPIValidationError(f"Path item {path} must be a mapping")
        for method in ("get", "post", "put", "patch", "delete", "options", "head"):
            operation = path_item.get(method)
            if operation is None:
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                raise OpenAPIValidationError(f"{method.upper()} {path} is missing operationId")
            if operation_id in seen:
                raise OpenAPIValidationError(f"Duplicate operationId: {operation_id}")
            seen.add(operation_id)
            responses = operation.get("responses")
            if not isinstance(responses, dict) or not responses:
                raise OpenAPIValidationError(f"{operation_id} is missing responses")


def validate_openapi_file(path: str | Path, require_library: bool = False) -> dict[str, Any]:
    spec_path = Path(path)
    try:
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OpenAPIValidationError(f"YAML parse failed: {exc}") from exc
    _basic_checks(spec)
    try:
        from openapi_spec_validator import validate
    except ImportError:
        if require_library:
            raise OpenAPIValidationError(
                "openapi-spec-validator is required; install requirements.txt"
            )
    else:
        try:
            validate(spec)
        except Exception as exc:
            raise OpenAPIValidationError(f"OpenAPI validation failed: {exc}") from exc
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an OpenAPI document before application startup")
    parser.add_argument("path", nargs="?", default="openapi.yaml")
    parser.add_argument("--strict", action="store_true", help="require openapi-spec-validator")
    args = parser.parse_args()
    spec = validate_openapi_file(args.path, require_library=args.strict)
    operation_ids = [
        operation["operationId"]
        for path_item in spec["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete", "options", "head"}
    ]
    print(f"PASS OpenAPI valid: {args.path} ({len(operation_ids)} operations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
