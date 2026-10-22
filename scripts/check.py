"""Проверка API после docker compose up --build."""

import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://localhost:8000"


def call(method, url, data=None):
    body = None if data is None else json.dumps(data).encode()
    request = Request(
        BASE + url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


product = {
    "name": "Мышь",
    "description": "USB-мышь",
    "price": 799.90,
    "stock": 12,
    "category": "Electronics",
    "status": "ACTIVE",
}

status, created = call("POST", "/products", product)
assert status == 201, (status, created)
product_id = created["id"]
print("Создание: OK")

status, found = call("GET", f"/products/{product_id}")
assert status == 200 and found["name"] == "Мышь"
print("Получение: OK")

status, listed = call(
    "GET", "/products?page=0&size=20&status=ACTIVE&category=Electronics"
)
assert status == 200 and any(item["id"] == product_id for item in listed["items"])
print("Список и фильтры: OK")

product["name"] = "Мышь обновлённая"
status, updated = call("PUT", f"/products/{product_id}", product)
assert status == 200 and updated["name"] == product["name"]
print("Обновление: OK")

status, error = call("POST", "/products", {**product, "price": -10})
assert (
    status == 400
    and error["error_code"] == "VALIDATION_ERROR"
    and "fields" in error["details"]
)
print("Валидация: OK")

status, archived = call("DELETE", f"/products/{product_id}")
assert status == 200 and archived["status"] == "ARCHIVED"
print("Мягкое удаление: OK")

status, missing = call("GET", "/products/999999999")
assert status == 404 and missing["error_code"] == "PRODUCT_NOT_FOUND"
print("Ошибка 404: OK")

print("Все проверки пройдены.")
