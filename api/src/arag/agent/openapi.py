"""SSE のイベント型を OpenAPI の components.schemas に載せる（web の TS 型生成用。R10）。"""

from typing import Any

from fastapi import FastAPI
from pydantic.json_schema import models_json_schema

from arag.agent.events import RUN_EVENT


def install_event_schemas(app: FastAPI) -> None:
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original()
        _, defs = models_json_schema([], ref_template="#/components/schemas/{model}")
        ev = RUN_EVENT.json_schema(ref_template="#/components/schemas/{model}")
        comps = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, d in {**defs.get("$defs", {}), **ev.pop("$defs", {})}.items():
            comps.setdefault(name, d)
        comps["RunEvent"] = ev
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
