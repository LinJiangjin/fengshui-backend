# -*- coding: utf-8 -*-
"""创建 / 更新管理后台账号。

用法（在 server 目录下执行）：
    python scripts/init_admin.py --username admin --password 'Admin@2026'
    python scripts/init_admin.py --username admin --password 'NewPass' --force

--force 会在账号已存在时直接重置密码（忘记密码时用）。
不加 --force 且账号已存在时，脚本只提示，不做任何修改。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.models import Admin  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.utils import new_id  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="创建或重置管理后台账号")
    parser.add_argument("--username", required=True, help="登录用户名")
    parser.add_argument("--password", required=True, help="登录密码，至少 6 位")
    parser.add_argument("--display-name", default="", help="显示名称，默认同用户名")
    parser.add_argument(
        "--force", action="store_true", help="账号已存在时重置其密码"
    )
    args = parser.parse_args()

    username = args.username.strip()
    if len(args.password) < 6:
        print("密码至少 6 位。")
        return 1

    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        admin = db.query(Admin).filter(Admin.username == username).one_or_none()
        if admin is None:
            admin = Admin(
                id=new_id("adm"),
                username=username,
                password_hash=hash_password(args.password),
                display_name=args.display_name.strip() or username,
                status="active",
            )
            db.add(admin)
            db.commit()
            print(f"已创建管理员：{username}（id={admin.id}）")
        elif args.force:
            admin.password_hash = hash_password(args.password)
            admin.status = "active"
            db.commit()
            print(f"已重置管理员密码并启用账号：{username}")
        else:
            print(f"管理员 {username} 已存在。如需重置密码请加 --force")
            return 1

    print("\n接下来即可在管理后台登录：")
    print("  前端启动后访问 /login，用上面这个用户名和密码登录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
