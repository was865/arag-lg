"""KB・フォルダ API の入出力。"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_FORBIDDEN = re.compile(r"[/\\\x00-\x1f\x7f]")


def _valid_name(v: str) -> str:
    v = v.strip()
    if not v or len(v) > 200 or _FORBIDDEN.search(v) or v in (".", ".."):
        raise ValueError("名前は 1〜200 文字で、/ や制御文字を含められません")
    return v


Name = Annotated[str, AfterValidator(_valid_name)]


class KbOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: Literal["personal", "org"]
    name: str
    status: Literal["active", "archived"]
    writable: bool
    document_count: int
    created_at: datetime
    role: Literal["viewer", "editor", "manager"] | None = Field(
        default=None, description="自分の役割（specs/024）。読めない KB（admin の管理用一覧）は null"
    )
    can_manage: bool = Field(default=False, description="共有リスト・名前・アーカイブ・削除を変えられるか")
    shared_with_everyone: bool = Field(default=False, description="共有リストに「全員」があるか")


class KbCreate(BaseModel):
    name: Name
    department_id: uuid.UUID | None = Field(
        default=None, description="部門向けに作る（既定の共有を「その部門: 閲覧」にする）。部門管理者は必須"
    )


class KbUpdate(BaseModel):
    name: Name


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kb_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    document_count: int
    created_at: datetime


class FolderCreate(BaseModel):
    name: Name
    parent_id: uuid.UUID | None = None


class FolderUpdate(BaseModel):
    """parent_id を明示的に null にするとルート直下へ移動する（未指定なら移動しない）。"""

    name: Name | None = None
    parent_id: uuid.UUID | None = None
