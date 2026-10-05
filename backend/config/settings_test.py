"""测试专用配置：本机无 PostgreSQL，用文件型 SQLite 跑测试。

文件型（而非 :memory:）是为了让多线程并发测试共享同一个库，
验证两名管理员交叉改同名时的数据库唯一约束兜底。
"""

import os
import tempfile

from .settings import *  # noqa: F401,F403

_fd, _path = tempfile.mkstemp(suffix=".sqlite3", prefix="sailcloth_test_")
os.close(_fd)
os.unlink(_path)  # 交由 Django 建库

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _path,
        "OPTIONS": {"timeout": 20},
    }
}
