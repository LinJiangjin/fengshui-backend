# -*- coding: utf-8 -*-
"""幂等迁移：给已存在的 houses 表补 owner_id 列与索引。

为什么需要单独跑：SQLAlchemy 的 `create_all` 只建「缺失的表」，
**不会**给已存在的表补列。用户体系上线前 houses 表已经建好了，
所以这里手工 ALTER 一次。

用法（在 server 目录下执行）：
    python scripts/migrate_owner_id.py

可重复执行：列/索引已存在时直接跳过。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app import models  # noqa: E402,F401  导入以注册模型

COLUMN = "owner_id"
TABLE = "houses"
INDEX = "ix_houses_owner_id"


def main() -> int:
    print("连接串 :", engine.url.render_as_string(hide_password=True))

    # 先确保新表（users / admins / sms_codes）建出来
    Base.metadata.create_all(bind=engine)
    print("已确保表存在:", ", ".join(sorted(Base.metadata.tables)))

    inspector = inspect(engine)
    if TABLE not in inspector.get_table_names():
        print(f"表 {TABLE} 尚不存在，create_all 已建好，无需补列。")
        return 0

    columns = {col["name"] for col in inspector.get_columns(TABLE)}
    if COLUMN in columns:
        print(f"列 {TABLE}.{COLUMN} 已存在，跳过。")
    else:
        dialect = engine.dialect.name
        # SQLite 与 PostgreSQL 都支持 ADD COLUMN（SQLite 需 3.2+）
        with engine.begin() as conn:
            conn.execute(
                text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} VARCHAR(64)")
            )
        print(f"已添加列 {TABLE}.{COLUMN}（{dialect}）")

    indexes = {idx["name"] for idx in inspector.get_indexes(TABLE)}
    if INDEX in indexes:
        print(f"索引 {INDEX} 已存在，跳过。")
    else:
        with engine.begin() as conn:
            conn.execute(
                text(f"CREATE INDEX {INDEX} ON {TABLE} ({COLUMN})")
            )
        print(f"已创建索引 {INDEX}")

    # 打印存量数据情况，便于确认有多少历史房屋没有归属
    with engine.connect() as conn:
        total = conn.execute(text(f'SELECT COUNT(*) FROM "{TABLE}"')).scalar()
        orphan = conn.execute(
            text(f'SELECT COUNT(*) FROM "{TABLE}" WHERE {COLUMN} IS NULL')
        ).scalar()
    print(f"houses 共 {total} 行，其中无归属 {orphan} 行（不会出现在任何用户列表里）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
