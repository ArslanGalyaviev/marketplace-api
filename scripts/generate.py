from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
spec_path = ROOT / "openapi/products.yaml"

if not spec_path.exists():
    raise FileNotFoundError(f"Не найден файл {spec_path}")

spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
out = ROOT / "app/generated"
out.mkdir(parents=True, exist_ok=True)
(out / "__init__.py").write_text("", encoding="utf-8")

schemas = spec["components"]["schemas"]
props = schemas["ProductFields"]["properties"]


def field_line(name, data, required):
    if "$ref" in data:
        kind = "ProductStatus"
    else:
        field_type = data["type"]
        if field_type == "string":
            kind = "str"
        elif field_type == "integer":
            kind = "int"
        elif field_type == "number":
            kind = "Decimal"
        elif field_type == "object":
            kind = "dict"
        elif field_type == "array":
            item_ref = data["items"]["$ref"].split("/")[-1]
            kind = f"list[{item_ref}]"
        else:
            raise ValueError(f"Неизвестный тип поля: {field_type}")

        if data.get("format") == "date-time":
            kind = "datetime"

    nullable = data.get("nullable", False)
    optional = name not in required or nullable
    if optional:
        kind += " | None"

    args = []
    if "minLength" in data:
        args.append(f"min_length={data['minLength']}")
    if "maxLength" in data:
        args.append(f"max_length={data['maxLength']}")
    if "minimum" in data:
        args.append(f"ge={data['minimum']}")
    if "maximum" in data:
        args.append(f"le={data['maximum']}")
    if "multipleOf" in data:
        args.append(f"multiple_of={data['multipleOf']}")
    if data.get("format") == "decimal":
        args.append("max_digits=12")
        args.append("decimal_places=2")

    default = "None" if optional else "..."
    if args:
        return f"    {name}: {kind} = Field({default}, {', '.join(args)})"
    return f"    {name}: {kind} = Field({default})"


lines = [
    "from datetime import datetime",
    "from decimal import Decimal",
    "from enum import Enum",
    "from pydantic import BaseModel, Field, ConfigDict, field_serializer",
    "",
    "class ProductStatus(str, Enum):",
]
for status in schemas["ProductStatus"]["enum"]:
    lines.append(f"    {status} = '{status}'")

for model_name in ("ProductCreate", "ProductUpdate", "ProductResponse"):
    schema = schemas[model_name]
    required = schema["required"]
    model_props = {**props, **schema.get("properties", {})}
    lines.extend(
        [
            "",
            f"class {model_name}(BaseModel):",
            "    model_config = ConfigDict(extra='forbid')",
        ]
    )
    for name, data in model_props.items():
        lines.append(field_line(name, data, required))

    if model_name == "ProductResponse":
        lines.extend(
            [
                "",
                "    @field_serializer('price')",
                "    def serialize_price(self, value):",
                "        return float(value)",
            ]
        )

for model_name in ("ProductPage", "ErrorResponse"):
    if model_name in schemas:
        schema = schemas[model_name]
        required = schema.get("required", [])
        model_props = schema.get("properties", {})
        lines.extend(
            [
                "",
                f"class {model_name}(BaseModel):",
            ]
        )
        for name, data in model_props.items():
            lines.append(field_line(name, data, required))

lines.append("")
(out / "models.py").write_text("\n".join(lines), encoding="utf-8")


routes = [
    "from fastapi import APIRouter, Path, Query",
    "from app.generated.models import ProductCreate, ProductUpdate, ProductResponse, ProductPage, ProductStatus, ErrorResponse",
    "from app import handlers",
    "router = APIRouter()",
    "",
]

for url, path_data in spec["paths"].items():
    path_params = path_data.get("parameters", [])

    for method, operation in path_data.items():
        if method not in ("get", "post", "put", "delete"):
            continue

        op_id = operation["operationId"]
        all_params = path_params + operation.get("parameters", [])
        args_list = []
        call_args = []

        if "requestBody" in operation:
            content = operation["requestBody"]["content"]["application/json"]
            schema_ref = content["schema"]["$ref"]
            schema_name = schema_ref.split("/")[-1]
            arg_name = "product"
            args_list.append(f"{arg_name}: {schema_name}")
            call_args.append(f"{arg_name}={arg_name}")

        for param in all_params:
            name = param["name"]
            param_in = param["in"]
            schema = param["schema"]

            if "$ref" in schema:
                type_name = schema["$ref"].split("/")[-1]
            else:
                type_name = {"integer": "int", "string": "str"}[schema["type"]]

            if param_in == "path":
                min_val = schema.get("minimum", 1)
                args_list.append(f"{name}: {type_name} = Path(..., ge={min_val})")
                call_args.append(f"{name}={name}")

            elif param_in == "query":
                default = schema.get("default", "None")
                if default == "None":
                    type_name += " | None"

                query_args = [str(default) if default != "None" else "None"]
                if "minimum" in schema:
                    query_args.append(f"ge={schema['minimum']}")

                args_list.append(
                    f"{name}: {type_name} = Query({', '.join(query_args)})"
                )
                call_args.append(f"{name}={name}")

        response_ref = operation["responses"].get(
            "200", operation["responses"].get("201")
        )["content"]["application/json"]["schema"]["$ref"]
        result_type = response_ref.split("/")[-1]
        code = 201 if method == "post" else 200

        error_responses = []
        for response_code in operation["responses"]:
            if response_code not in ("200", "201"):
                error_responses.append(
                    f"{int(response_code)}: {{'model': ErrorResponse}}"
                )
        responses_str = "{" + ", ".join(error_responses) + "}"

        func_args_str = ", ".join(args_list)
        routes.append(
            f"@router.{method}('{url}', response_model={result_type}, "
            f"status_code={code}, responses={responses_str})"
        )
        routes.append(f"def {op_id}({func_args_str}):")
        routes.append(f"    return handlers.{op_id}({', '.join(call_args)})")
        routes.append("")

(out / "routes.py").write_text("\n".join(routes), encoding="utf-8")
print("Готово")
