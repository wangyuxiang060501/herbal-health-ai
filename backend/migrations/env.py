"""Alembic 迁移环境（清单 1.3.3 / 1.3.4）

连接串与模型元数据都取自应用自身配置，保证「迁移视角」与「运行视角」
永远看同一套真相：
  - DATABASE_URL 来自 app.core.config.settings（.env 优先，其次 .env.example 默认值）；
  - target_metadata 是 app.models.entities 的 Base.metadata，
    `alembic revision --autogenerate` 才能对比出真实差异。
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

# 应用配置接管 sqlalchemy.url（alembic.ini 里只留占位说明）
from app.core.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入全部模型后取元数据（app.models 会级联导入所有实体类）
from app.core.database import Base  # noqa: E402
from app.models import entities  # noqa: E402,F401  确保表定义全部注册

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 不连库"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite 变更列/索引需要 batch 模式
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite 变更列/索引需要 batch 模式
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
