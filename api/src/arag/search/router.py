"""POST /v1/search（評価・診断用。specs/004-retrieval R17）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from arag.deps import CtxDep
from arag.errors import ApiError
from arag.search.schemas import SearchRequest, SearchResult
from arag.search.service import SearchDeps, search

router = APIRouter(prefix="/v1", tags=["search"])


def get_search_deps(request: Request) -> SearchDeps:
    deps: SearchDeps = request.app.state.search_deps
    return deps


@router.post("/search", response_model=SearchResult)
async def search_endpoint(
    body: SearchRequest, ctx: CtxDep, deps: Annotated[SearchDeps, Depends(get_search_deps)]
) -> SearchResult:
    # エージェントは同じ関数を直接呼ぶ。HTTP での検索は管理者の診断・評価に限る
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "この操作は管理者だけが行えます")
    return await search(ctx.session, deps, ctx.principal, body)
