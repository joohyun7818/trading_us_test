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
        conn.autocommit = True
        cursor = conn.cursor()

        statements = schema_sql.split(";")
        executed = 0
        errors = 0

        for stmt in statements:
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                continue
            try:
                cursor.execute(stmt + ";")
                executed += 1
            except psycopg2.Error as e:
                error_msg = str(e).strip()
                if "already exists" in error_msg:
                    logger.info("Skipped (already exists): %s...", stmt[:60])
                else:
                    logger.error("SQL error: %s\nStatement: %s...", error_msg, stmt[:80])
                    errors += 1

        cursor.close()
        conn.close()

        logger.info("Database initialization complete: %d executed, %d errors", executed, errors)

    except psycopg2.Error as e:
        logger.error("Database connection failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
