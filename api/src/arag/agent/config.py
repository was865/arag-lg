"""エージェント挙動設定とモデル目録（specs/005-agent R24・R28・R29）。"""

from dataclasses import dataclass, field, fields, replace
from typing import Any

from langchain_core.language_models import BaseChatModel

from arag.llm import chat_model, has_credentials


class ModelNotFound(Exception):
    pass


def _int(v: Any, lo: int, hi: int, default: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return default
    return max(lo, min(hi, round(v)))


def _float(v: Any, lo: float, hi: float, default: float) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return default
    return max(lo, min(hi, float(v)))


def _bool(v: Any, default: bool) -> bool:
    return v if isinstance(v, bool) else default


@dataclass(frozen=True, slots=True)
class AgentCfg:
    max_steps: int = 12
    parallel_tools: int = 3
    top_k: int = 6
    # 1 文書から返す件数の上限（0 で無制限）。複数資料の照合を 1 回の検索で拾えるようにする
    per_document: int = 3
    candidate_k: int = 30
    max_retrieve_retries: int = 1
    grade_threshold: float = 0.3
    require_citations: bool = True
    admit_unknown: bool = True
    verify: bool = False
    # 回答のあとに続けて聞く質問の候補を作る（利用者の設定。specs/028 R7）
    followups: bool = True

    @classmethod
    def clamped(cls, raw: Any) -> "AgentCfg":
        """利用者・ブラウザ由来の任意の値を、常に有効な設定にする（範囲外は丸め、型違いは既定）。"""
        o: dict[str, Any] = raw if isinstance(raw, dict) else {}
        d = cls()
        top_k = _int(o.get("top_k"), 1, 20, d.top_k)
        return cls(
            max_steps=_int(o.get("max_steps"), 5, 20, d.max_steps),
            parallel_tools=_int(o.get("parallel_tools"), 1, 8, d.parallel_tools),
            top_k=top_k,
            per_document=_int(o.get("per_document"), 0, 20, d.per_document),
            # 候補数は最終件数以上でなければ意味が無いので引き上げる
            candidate_k=max(_int(o.get("candidate_k"), 1, 50, d.candidate_k), top_k),
            max_retrieve_retries=_int(o.get("max_retrieve_retries"), 0, 2, d.max_retrieve_retries),
            grade_threshold=_float(o.get("grade_threshold"), 0.0, 1.0, d.grade_threshold),
            require_citations=_bool(o.get("require_citations"), d.require_citations),
            admit_unknown=_bool(o.get("admit_unknown"), d.admit_unknown),
            verify=_bool(o.get("verify"), d.verify),
            followups=_bool(o.get("followups"), d.followups),
        )

    def as_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def with_(self, **kw: Any) -> "AgentCfg":
        return replace(self, **kw)


@dataclass(frozen=True, slots=True)
class ModelSpec:
    id: str
    label: str
    model: str
    base_url: str = ""
    kwargs: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    available: bool = False
    # 画面で登録した接続の鍵（ログ・repr に出さない）
    api_key: str = field(default="", repr=False)
    source: str = "env"  # env / db

    def build(self) -> BaseChatModel:
        return chat_model(self.model, base_url=self.base_url, kwargs=self.kwargs, api_key=self.api_key)


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """モデル目録（DB と ARAG_CHAT_MODELS の合成は arag.agent.catalog）。先頭の利用可能なものが既定。"""

    models: tuple[ModelSpec, ...]

    @classmethod
    def from_raw(cls, raw: list[dict[str, Any]]) -> "ModelCatalog":
        out = []
        for r in raw:
            spec = ModelSpec(
                id=str(r["id"]),
                label=str(r.get("label") or r["id"]),
                model=str(r["model"]),
                base_url=str(r.get("base_url") or ""),
                kwargs=dict(r.get("kwargs") or {}),
                tags=tuple(r.get("tags") or ()),
            )
            out.append(replace(spec, available=has_credentials(spec.model, spec.base_url)))
        return cls(tuple(out))

    def default(self) -> ModelSpec:
        for m in self.models:
            if m.available:
                return m
        raise ModelNotFound("利用できるモデルがありません（ARAG_CHAT_MODELS と API キーを確認してください）")

    def resolve(self, model_id: str | None) -> ModelSpec:
        if model_id is None:
            return self.default()
        for m in self.models:
            if m.id == model_id and m.available:
                return m
        raise ModelNotFound(f"モデル {model_id} は利用できません")

    def fallback(self, model_id: str) -> ModelSpec | None:
        """代替モデル: 目録で次の利用可能なもの（末尾なら先頭へ戻る）。"""
        ids = [m.id for m in self.models]
        if model_id not in ids:
            return None
        i = ids.index(model_id)
        for m in self.models[i + 1 :] + self.models[:i]:
            if m.available:
                return m
        return None
