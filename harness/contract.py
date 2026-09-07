from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator


@dataclass
class ContractValidationError(AssertionError):
    operation_id: str
    phase: str
    detail: str

    def __str__(self) -> str:
        return f"{self.operation_id} [{self.phase}] {self.detail}"


class OpenAPIContract:
    """Reusable request/response judge driven only by an OpenAPI document."""

    HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}

    def __init__(self, spec_path: str | Path, require_openapi_core: bool = False):
        self.spec_path = Path(spec_path)
        self.spec = yaml.safe_load(self.spec_path.read_text(encoding="utf-8"))
        self._routes = self._compile_routes()
        self._openapi = None
        try:
            from openapi_core import OpenAPI
        except ImportError:
            if require_openapi_core:
                raise RuntimeError("openapi-core is required; install requirements.txt")
            self.engine = "jsonschema-fallback"
        else:
            self._openapi = OpenAPI.from_file_path(str(self.spec_path))
            self.engine = "openapi-core"

    def _compile_routes(self) -> list[tuple[str, re.Pattern[str], str, dict[str, Any]]]:
        routes = []
        for template, path_item in self.spec.get("paths", {}).items():
            escaped = re.escape(template)
            pattern = re.sub(r"\\\{([^{}]+)\\\}", r"(?P<\1>[^/]+)", escaped)
            regex = re.compile(f"^{pattern}$")
            for method, operation in path_item.items():
                if method in self.HTTP_METHODS:
                    routes.append((method.upper(), regex, template, operation))
        return routes

    def operation_for(self, method: str, path: str) -> tuple[str, str, dict[str, str], dict[str, Any]]:
        clean_path = path.split("?", 1)[0]
        for route_method, regex, template, operation in self._routes:
            if route_method != method.upper():
                continue
            match = regex.match(clean_path)
            if match:
                return operation["operationId"], template, match.groupdict(), operation
        raise ContractValidationError("<unknown>", "routing", f"No OpenAPI operation for {method.upper()} {clean_path}")

    def validate_request(
        self,
        method: str,
        path: str,
        request_json: Any,
        headers: dict[str, str] | None = None,
    ) -> str:
        operation_id, _, _, _ = self.operation_for(method, path)
        self._fallback_validate_request(method, path, request_json)
        if self._openapi is not None:
            try:
                openapi_request, _ = self._make_core_request(
                    method, path, request_json, headers or {}
                )
                self._openapi.validate_request(openapi_request)
            except ContractValidationError:
                raise
            except Exception as exc:
                raise ContractValidationError(operation_id, "request", str(exc)) from exc
        return operation_id

    def validate_response(
        self,
        method: str,
        path: str,
        request_json: Any,
        response_status: int,
        response_json: Any,
        headers: dict[str, str] | None = None,
    ) -> str:
        operation_id, _, _, _ = self.operation_for(method, path)
        self._fallback_validate_response(method, path, response_status, response_json)
        if self._openapi is not None:
            try:
                from openapi_core.contrib.requests import RequestsOpenAPIResponse
                from requests import Response

                openapi_request, prepared = self._make_core_request(
                    method, path, request_json, headers or {}
                )
                response = Response()
                response.status_code = int(response_status)
                response.headers["Content-Type"] = "application/json"
                response._content = (
                    json.dumps(response_json).encode("utf-8")
                    if response_json is not None
                    else b""
                )
                response.request = prepared
                self._openapi.validate_response(
                    openapi_request, RequestsOpenAPIResponse(response)
                )
            except ContractValidationError:
                raise
            except Exception as exc:
                raise ContractValidationError(operation_id, "response", str(exc)) from exc
        return operation_id

    def validate_exchange(
        self,
        method: str,
        path: str,
        request_json: Any,
        response_status: int,
        response_json: Any,
        headers: dict[str, str] | None = None,
    ) -> str:
        operation_id = self.validate_request(method, path, request_json, headers)
        self.validate_response(
            method,
            path,
            request_json,
            response_status,
            response_json,
            headers,
        )
        return operation_id

    @staticmethod
    def _make_core_request(
        method: str,
        path: str,
        request_json: Any,
        headers: dict[str, str],
    ):
        from openapi_core.contrib.requests import RequestsOpenAPIRequest
        from requests import Request, Session

        req_headers = dict(headers)
        if request_json is not None:
            req_headers.setdefault("Content-Type", "application/json")
        request = Request(
            method=method.upper(),
            url=f"http://localhost{path}",
            json=request_json if request_json is not None else None,
            headers=req_headers,
        )
        prepared = Session().prepare_request(request)
        return RequestsOpenAPIRequest(request), prepared

    def _fallback_validate_request(self, method: str, path: str, request_json: Any) -> None:
        operation_id, template, path_params, operation = self.operation_for(method, path)
        parameters = list(self.spec["paths"][template].get("parameters", [])) + list(operation.get("parameters", []))
        for raw_parameter in parameters:
            parameter = self._resolve_ref_node(raw_parameter)
            if parameter.get("in") == "path":
                name = parameter["name"]
                if parameter.get("required") and name not in path_params:
                    raise ContractValidationError(operation_id, "request", f"Missing path parameter {name}")
                if name in path_params:
                    self._validate_scalar(path_params[name], parameter.get("schema", {}), operation_id, name)
        request_body = operation.get("requestBody")
        if request_body:
            request_body = self._resolve_ref_node(request_body)
            if request_json is None and request_body.get("required"):
                raise ContractValidationError(operation_id, "request", "Missing required JSON request body")
            if request_json is not None:
                schema = self._content_schema(request_body)
                self._validate_json(request_json, schema, operation_id, "request")
        elif request_json is not None:
            raise ContractValidationError(operation_id, "request", "Operation does not define a request body")

    def _fallback_validate_response(self, method: str, path: str, status: int, body: Any) -> None:
        operation_id, _, _, operation = self.operation_for(method, path)
        responses = operation.get("responses", {})
        response = responses.get(str(status)) or responses.get("default")
        if response is None:
            raise ContractValidationError(operation_id, "response", f"Undeclared HTTP status {status}")
        response = self._resolve_ref_node(response)
        content = response.get("content", {})
        if not content:
            if body not in (None, "", b""):
                raise ContractValidationError(operation_id, "response", "Response body is not allowed")
            return
        schema = self._content_schema(response)
        self._validate_json(body, schema, operation_id, "response")

    def _resolve_ref_node(self, node: dict[str, Any]) -> dict[str, Any]:
        current = node
        seen: set[str] = set()
        while isinstance(current, dict) and "$ref" in current:
            ref = current["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise ValueError(f"Only local OpenAPI refs are supported by the fallback: {ref}")
            if ref in seen:
                raise ValueError(f"Circular OpenAPI ref: {ref}")
            seen.add(ref)
            target: Any = self.spec
            for token in ref[2:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                target = target[token]
            current = target
        return current

    @staticmethod
    def _content_schema(container: dict[str, Any]) -> dict[str, Any]:
        content = container.get("content", {})
        media = content.get("application/json")
        if not media or "schema" not in media:
            raise ValueError("Harness supports application/json schemas for this project")
        return media["schema"]

    def _validate_json(self, value: Any, schema: dict[str, Any], operation_id: str, phase: str) -> None:
        schema_copy = self._jsonschema_compatible(copy.deepcopy(schema))
        root_copy = self._jsonschema_compatible(copy.deepcopy(self.spec))
        # Validate through the OpenAPI root so local references in the selected
        # schema (for example, ``#/components/schemas/Foo``) retain their scope.
        root_copy["x-harness-validation-schema"] = schema_copy
        root_copy["$ref"] = "#/x-harness-validation-schema"
        validator = Draft7Validator(root_copy)
        errors = sorted(validator.iter_errors(value), key=lambda e: list(e.path))
        if errors:
            err = errors[0]
            where = ".".join(str(p) for p in err.path) or "body"
            raise ContractValidationError(operation_id, phase, f"{where}: {err.message}")

    @classmethod
    def _jsonschema_compatible(cls, node: Any) -> Any:
        if isinstance(node, dict):
            converted = {k: cls._jsonschema_compatible(v) for k, v in node.items() if k != "nullable"}
            if node.get("nullable") is True and "$ref" not in converted:
                original = dict(converted)
                return {"anyOf": [original, {"type": "null"}]}
            return converted
        if isinstance(node, list):
            return [cls._jsonschema_compatible(item) for item in node]
        return node

    @staticmethod
    def _validate_scalar(raw: str, schema: dict[str, Any], operation_id: str, name: str) -> None:
        expected = schema.get("type")
        if expected == "integer":
            try:
                value = int(raw)
            except (TypeError, ValueError) as exc:
                raise ContractValidationError(operation_id, "request", f"Path parameter {name} must be integer") from exc
            if "minimum" in schema and value < schema["minimum"]:
                raise ContractValidationError(operation_id, "request", f"Path parameter {name} is below minimum")


class ContractClient:
    """Wrap a normal HTTP-style test client and judge each exchange against OpenAPI."""

    def __init__(self, client: Any, contract: OpenAPIContract):
        self.client = client
        self.contract = contract

    def request(self, method: str, path: str, *, json_body: Any = None):
        operation_id = self.contract.validate_request(method, path, json_body)
        response = self.client.open(path, method=method.upper(), json=json_body)
        response_body = response.get_json(silent=True)
        self.contract.validate_response(
            method,
            path,
            json_body,
            response.status_code,
            response_body,
            dict(response.headers),
        )
        setattr(response, "operation_id", operation_id)
        return response

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, json: Any):
        return self.request("POST", path, json_body=json)

    def patch(self, path: str, json: Any):
        return self.request("PATCH", path, json_body=json)
