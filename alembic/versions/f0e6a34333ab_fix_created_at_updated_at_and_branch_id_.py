"""fix created_at updated_at and branch_id flow

Revision ID: f0e6a34333ab
Revises: 58d540609a86
Create Date: 2025-08-24 03:03:15.160086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0e6a34333ab'
down_revision: Union[str, Sequence[str], None] = '58d540609a86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ใช้คำสั่งดิบเพราะต้อง IF NOT EXISTS / ตรวจ constraint/index
def upgrade() -> None:
    conn = op.get_bind()

    # 1) สร้างตาราง branches ถ้ายังไม่มี
    conn.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS branches (
        id   SERIAL PRIMARY KEY,
        name VARCHAR NOT NULL
    );
    """))
    # index (ถ้ายังไม่มี)
    conn.execute(sa.text("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'ix_branches_id' AND n.nspname = 'public'
        ) THEN
            CREATE INDEX ix_branches_id ON branches (id);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'ix_branches_name' AND n.nspname = 'public'
        ) THEN
            CREATE INDEX ix_branches_name ON branches (name);
        END IF;
    END$$;
    """))

    # 2) เติมคอลัมน์ใน products ถ้ายังไม่มี
    conn.execute(sa.text("""
    ALTER TABLE products
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL,
        ADD COLUMN IF NOT EXISTS branch_id INTEGER NULL;
    """))

    # 3) ใส่สาขาเริ่มต้น แล้วเซ็ต branch_id ให้แถวที่ยัง NULL
    conn.execute(sa.text("INSERT INTO branches (name) SELECT 'Main Branch' WHERE NOT EXISTS (SELECT 1 FROM branches WHERE name='Main Branch');"))
    res = conn.execute(sa.text("SELECT id FROM branches WHERE name='Main Branch' LIMIT 1;")).fetchone()
    default_branch_id = res[0]
    conn.execute(sa.text("UPDATE products SET branch_id = :bid WHERE branch_id IS NULL;"), {"bid": default_branch_id})

    # 4) สร้าง index ที่ต้องใช้ (ถ้ายังไม่มี)
    conn.execute(sa.text("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'ix_products_branch_id' AND n.nspname = 'public'
        ) THEN
            CREATE INDEX ix_products_branch_id ON products (branch_id);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'ix_products_name_category_branch' AND n.nspname = 'public'
        ) THEN
            CREATE INDEX ix_products_name_category_branch ON products (name, category, branch_id);
        END IF;
    END$$;
    """))

    # 5) ใส่ FK (ถ้ายังไม่มี) แล้วค่อยล็อก NOT NULL
    conn.execute(sa.text("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_branch_id'
        ) THEN
            ALTER TABLE products
            ADD CONSTRAINT fk_products_branch_id
            FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE RESTRICT;
        END IF;
    END$$;
    """))

    conn.execute(sa.text("ALTER TABLE products ALTER COLUMN branch_id SET NOT NULL;"))


def downgrade() -> None:
    conn = op.get_bind()
    # คลาย NOT NULL / ลบ FK / ลบ index / ลบคอลัมน์ อย่างมีเงื่อนไข
    conn.execute(sa.text("""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_branch_id') THEN
            ALTER TABLE products DROP CONSTRAINT fk_products_branch_id;
        END IF;
    END$$;
    """))
    conn.execute(sa.text("""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE c.relname = 'ix_products_name_category_branch' AND n.nspname = 'public') THEN
            DROP INDEX ix_products_name_category_branch;
        END IF;
        IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE c.relname = 'ix_products_branch_id' AND n.nspname = 'public') THEN
            DROP INDEX ix_products_branch_id;
        END IF;
    END$$;
    """))
    conn.execute(sa.text("""
    ALTER TABLE products
        DROP COLUMN IF EXISTS branch_id,
        DROP COLUMN IF EXISTS updated_at,
        DROP COLUMN IF EXISTS created_at;
    """))

    conn.execute(sa.text("""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='public' AND table_name='branches') THEN
            DROP TABLE branches;
        END IF;
    END$$;
    """))
