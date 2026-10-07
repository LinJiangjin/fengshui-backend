# -*- coding: utf-8 -*-
"""数据库连接层：SQLAlchemy 2.0 引擎 + 请求级会话管理。

用法（路由中注入会话）：

    from fastapi import Depends
    from sqlalchemy.orm import Session
    from ..db import get_db

    @router.get("/xxx")
    def xxx(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    """ORM 模型基类。当前版本未建业务表，后续建表时继承此类即可。"""


def _engine_kwargs() -> dict:
    """按方言拼连接参数；SQLite 放开跨线程，其余保留连接池设置。"""
    if DATABASE_URL.startswith("sqlite"):
        # FastAPI 可能在多个线程里用同一个连接，SQLite 默认禁止跨线程
        return {"connect_args": {"check_same_thread": False}, "future": True}
    return {
        "pool_pre_ping": True,  # 连接失效自动重连，数据库重启后不需要重启后端
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 1800,  # 回收长连接，规避被防火墙静默断开
        "future": True,
    }


engine: Engine = create_engine(DATABASE_URL, **_engine_kwargs())

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：一次请求一个会话，响应结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping() -> tuple[bool, str]:
    """连通性自检，返回 (是否连通, 说明)。捕获异常，供 /health 安全调用。"""
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "postgresql":
                dbname = conn.execute(text("SELECT current_database()")).scalar()
                version = conn.execute(text("SHOW server_version")).scalar()
                return True, f"{dbname} (PostgreSQL {version})"
            # SQLite 等轻量库只探活
            conn.execute(text("SELECT 1"))
            return True, f"{engine.dialect.name}: {engine.url.database}"
    except SQLAlchemyError as exc:  # 连接失败、认证失败等
        return False, f"{exc.__class__.__name__}: {str(getattr(exc, 'orig', exc))[:200]}"
