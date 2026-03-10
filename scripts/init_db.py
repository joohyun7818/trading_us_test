#!/usr/bin/env python3
"""독립 실행 스크립트: .env에서 DATABASE_URL 로드, schema.sql 실행."""
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """schema.sql을 읽어 PostgreSQL에 실행한다."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        logger.warning("python-dotenv not installed, using system env only")

    database_url = os.getenv("DATABASE_URL", "postgresql://alphaflow:alphaflow123@localhost:5432/alphaflow_us")

    if database_url.startswith("postgresql://"):
        dsn = database_url.replace("postgresql://", "postgres://", 1)
    else:
        dsn = database_url

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    schema_path = os.path.join(project_root, "api", "models", "schema.sql")

    if not os.path.isfile(schema_path):
        logger.error("schema.sql not found at: %s", schema_path)
        sys.exit(1)

    logger.info("Reading schema from: %s", schema_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    logger.info("Connecting to database...")
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
        cursor = conn.cursor()

        # schema.sql 전체를 하나의 트랜잭션으로 실행
        cursor.execute(schema_sql)
        conn.commit()

        logger.info("Database initialization complete: all statements executed successfully")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        logger.error("SQL execution failed: %s", str(e).strip())
        conn.rollback()
        conn.close()
        sys.exit(1)


if __name__ == "__main__":
    main()

