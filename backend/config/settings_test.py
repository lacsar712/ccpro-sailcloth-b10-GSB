from config.settings import *  # noqa: F401,F403

# 本地/CI 无 PostgreSQL 时跑测试用 SQLite。
# 用文件库而非内存库：并发改名测试需跨线程共享同一数据库。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {
            "NAME": str(BASE_DIR / ".test_sqlite.db"),  # noqa: F405
        },
    }
}
