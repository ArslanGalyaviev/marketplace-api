import os
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException
from app.generated.models import ProductResponse, ProductPage

PRODUCT_COLUMNS = (
    "id, name, description, price, stock, category, status, created_at, updated_at"
)


def connection():
    return psycopg.connect(
        os.getenv(
            "DATABASE_URL", "postgresql://student:student@localhost:5432/marketplace"
        ),
        row_factory=dict_row,
    )


def find_product(db, id):
    row = db.execute(
        f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = %s", (id,)
    ).fetchone()
    if row is None:
        raise HTTPException(
            404,
            detail={"error_code": "PRODUCT_NOT_FOUND", "message": "Товар не найден"},
        )
    return row


def create_product(product):
    with connection() as db:
        row = db.execute(
            f"""
            INSERT INTO products (name, description, price, stock, category, status)
            VALUES (%s, %s, %s, %s, %s, %s) 
            RETURNING {PRODUCT_COLUMNS}
        """,
            (
                product.name,
                product.description,
                product.price,
                product.stock,
                product.category,
                product.status.value,
            ),
        ).fetchone()
    return ProductResponse(**row)


def get_product(id):
    with connection() as db:
        row = find_product(db, id)
    return ProductResponse(**row)


def list_products(page, size, status, category):
    conditions = []
    values = []
    if status is not None:
        conditions.append("status = %s")
        values.append(status.value)
    if category is not None:
        conditions.append("category = %s")
        values.append(category)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    with connection() as db:
        total = db.execute(
            "SELECT COUNT(*) AS count FROM products" + where, values
        ).fetchone()["count"]
        rows = db.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM products"
            + where
            + " ORDER BY id LIMIT %s OFFSET %s",
            values + [size, page * size],
        ).fetchall()

    return ProductPage(
        items=[ProductResponse(**row) for row in rows],
        totalElements=total,
        page=page,
        size=size,
    )


def update_product(id, product):
    with connection() as db:
        find_product(db, id)
        row = db.execute(
            f"""
            UPDATE products SET name=%s, description=%s, price=%s,
            stock=%s, category=%s, status=%s
            WHERE id=%s 
            RETURNING {PRODUCT_COLUMNS}
        """,
            (
                product.name,
                product.description,
                product.price,
                product.stock,
                product.category,
                product.status.value,
                id,
            ),
        ).fetchone()
    return ProductResponse(**row)


def archive_product(id):
    with connection() as db:
        find_product(db, id)
        row = db.execute(
            f"UPDATE products SET status='ARCHIVED' WHERE id=%s RETURNING {PRODUCT_COLUMNS}",
            (id,),
        ).fetchone()
    return ProductResponse(**row)
