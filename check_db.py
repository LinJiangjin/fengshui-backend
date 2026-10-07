# -*- coding: utf-8 -*-
"""数据库连接自检脚本。

用法：
    python check_db.py

输出连接串（隐藏口令）、连通性结果与数据库版本。退出码 0 表示连通。
"""

from app.db import Base, engine, ping
from app import models  # noqa: F401  导入以注册 ORM 模型，create_all 才能建表


def main() -> int:
    print("连接串 :", engine.url.render_as_string(hide_password=True))
    ok, info = ping()
    print("连通性 :", "OK" if ok else "FAILED")
    print("详情   :", info)
    if ok:
        # 自检顺带建表（只创建缺失的表，无破坏性），等价于应用启动时的行为
        Base.metadata.create_all(bind=engine)
        # 打印各业务表行数，便于确认数据落在了哪个库
        from sqlalchemy import text

        with engine.connect() as conn:
            for name in sorted(Base.metadata.tables):
                try:
                    n = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
                    print(f"表 {name}: {n} 行")
                except Exception as exc:  # 表存在但查询失败等
                    print(f"表 {name}: 查询失败 {exc}")
    if not ok:
        print("\n排查建议：")
        print("  1. 数据库是否已启动：D:\\Dev\\pgsql\\start.bat")
        print("  2. 端口是否被占用：netstat -ano | findstr 5432")
        print("  3. 库与账号是否存在：重新运行 D:\\Dev\\pgsql\\setup.bat")
        print("  4. 口令是否与 .env 一致")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
