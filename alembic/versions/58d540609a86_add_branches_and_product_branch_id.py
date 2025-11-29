from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "58d540609a86"
down_revision = "12eb77a37e2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) สร้างตาราง branches ก่อน
    op.create_table(
        'branches',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(), nullable=False, index=True),
    )
    op.create_index('ix_branches_id', 'branches', ['id'])
    op.create_index('ix_branches_name', 'branches', ['name'])

    # 2) เพิ่มคอลัมน์ใหม่ใน products แบบที่ "ไม่ล็อก NOT NULL ทันที"
    #    - created_at ให้ default now() เพื่อให้แถวเก่าไม่ error
    #    - updated_at ให้เป็น nullable ได้
    #    - branch_id เริ่มจาก nullable ก่อน
    op.add_column('products', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('products', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('products', sa.Column('branch_id', sa.Integer(), nullable=True))

    # 3) สร้างสาขาเริ่มต้น (Default Branch) แล้วอัปเดตแถวเก่าให้มี branch_id
    conn = op.get_bind()

    # แทรก default branch ถ้ายังไม่มี
    result = conn.execute(sa.text("SELECT id FROM branches WHERE name = :name"), {"name": "Main Branch"}).fetchone()
    if result is None:
        conn.execute(sa.text("INSERT INTO branches (name) VALUES (:name)"), {"name": "Main Branch"})
        result = conn.execute(sa.text("SELECT id FROM branches WHERE name = :name"), {"name": "Main Branch"}).fetchone()

    default_branch_id = result[0]

    # เซ็ต branch_id ให้ทุก products ที่ยังเป็น NULL
    conn.execute(sa.text("UPDATE products SET branch_id = :bid WHERE branch_id IS NULL"), {"bid": default_branch_id})

    # 4) ค่อยใส่ constraint / index หลังจากข้อมูลพร้อมแล้ว
    op.create_index('ix_products_branch_id', 'products', ['branch_id'])
    op.create_index('ix_products_name_category_branch', 'products', ['name', 'category', 'branch_id'])

    # ใส่ FK
    op.create_foreign_key(
        'fk_products_branch_id',
        'products', 'branches',
        ['branch_id'], ['id'],
        ondelete='RESTRICT'
    )

    # 5) เปลี่ยน branch_id ให้ NOT NULL ตอนนี้ได้แล้ว
    op.alter_column('products', 'branch_id', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    # ลบ FK และ index ก่อน
    op.drop_constraint('fk_products_branch_id', 'products', type_='foreignkey')
    op.drop_index('ix_products_name_category_branch', table_name='products')
    op.drop_index('ix_products_branch_id', table_name='products')

    # ลบคอลัมน์จาก products
    op.drop_column('products', 'branch_id')
    op.drop_column('products', 'updated_at')
    op.drop_column('products', 'created_at')

    # ลบ branches
    op.drop_index('ix_branches_name', table_name='branches')
    op.drop_index('ix_branches_id', table_name='branches')
    op.drop_table('branches')
