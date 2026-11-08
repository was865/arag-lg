"""1 行 1 JSON の構造化ログ。request_id は contextvars 経由で全行に付く。"""

import logging
import sys

import structlog


def _rename_fields(
    _logger: object, _method: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    # 出力キーを ts / level / msg / logger に揃える（旧版のログ形式と同じ）
    event_dict["msg"] = event_dict.pop("event", "")
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """structlog と標準 logging（uvicorn 等）を同じ JSON 形式で標準出力へ流す。"""
    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.format_exc_info,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _rename_fields,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )

    class _StdoutHandler(logging.StreamHandler):  # type: ignore[type-arg]
        """毎回 sys.stdout を引き直す（テストの出力捕捉と差し替えに追従するため）。"""

        @property
        def stream(self) -> object:
            return sys.stdout

        @stream.setter
        def stream(self, _value: object) -> None:
            pass

    handler = _StdoutHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    # アクセスログは RequestIdMiddleware が構造化して出すため uvicorn 側は止める（重複防止）
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)
