# -*- coding: utf-8 -*-
"""合规文档路由：用户协议与隐私政策。

    GET /api/v1/legal/documents    文档清单（标题 + 版本 + 更新时间）
    GET /api/v1/legal/{slug}       单篇全文（分节结构化，客户端直接渲染）

条款正文不写死在客户端：一是商店审核要求隐私政策可及时更新，
二是登录页的链接文案也应由服务端下发，避免两处文案对不上。

正文当前维护在 app/legal_docs.py；迁到数据库时本文件无需改动。
"""

from fastapi import APIRouter, HTTPException, status

from ..legal_docs import LEGAL_DOC_ORDER, LEGAL_DOCS

router = APIRouter(prefix="/api/v1/legal", tags=["legal"])


def ok(data):
    return {"code": 0, "status": "ok", "data": data}


# 注意：/documents 必须声明在 /{slug} 之前，否则会被动态段吞掉
@router.get("/documents")
def list_documents():
    """文档清单。客户端据此渲染登录页的《用户协议》《隐私政策》链接。"""
    items = [
        {
            "slug": slug,
            "title": LEGAL_DOCS[slug]["title"],
            "version": LEGAL_DOCS[slug]["version"],
            "updated_at": LEGAL_DOCS[slug]["updated_at"],
            "summary": LEGAL_DOCS[slug]["summary"],
        }
        for slug in LEGAL_DOC_ORDER
        if slug in LEGAL_DOCS
    ]
    return ok({"items": items})


@router.get("/{slug}")
def get_document(slug: str):
    """单篇全文，按节返回。未知 slug 返回 404。"""
    doc = LEGAL_DOCS.get(slug)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在或已下线"
        )
    return ok(doc)
