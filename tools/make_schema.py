#!/usr/bin/env python3
"""Write ``database/schema.sql`` from the SQLAlchemy models.

It only reads the model files (with Python's ``ast`` module), so it needs neither Flask nor a database:

    python tools/make_schema.py            # rewrite database/schema.sql
    python tools/make_schema.py --check    # exit status 1 when database/schema.sql no longer matches the models

Most people never need the SQL file: ``python init_db.py`` builds the same tables straight from the models.
The file exists for anyone who prefers to create the tables with the ``mysql`` command line or MySQL Workbench.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "app" / "models"
OUTPUT = ROOT / "database" / "schema.sql"
DATABASE_NAME = "pawconnect_db"

_NO_DEFAULT = object()
SIMPLE_TYPES = {"Integer": "INT", "Text": "TEXT", "Boolean": "TINYINT(1)", "DateTime": "DATETIME", "Date": "DATE"}


class SchemaError(Exception):
    pass


def _is_db(node, name):
    return isinstance(node, ast.Attribute) and node.attr == name and isinstance(node.value, ast.Name) and node.value.id == "db"


def _const(node):
    if isinstance(node, ast.Constant):
        return node.value
    raise SchemaError(f"expected a literal value, found {ast.dump(node)}")


def _sql_type(node):
    """``db.Integer`` / ``db.String(80)`` / ``db.Float(53)`` -> MySQL column type."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "db":
        name, args = node.attr, []
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        name, args = node.func.attr, [_const(a) for a in node.args]
    else:
        raise SchemaError(f"unknown column type {ast.dump(node)}")
    if name == "String":
        return f"VARCHAR({args[0]})"
    if name == "Float":
        return "DOUBLE" if args and args[0] == 53 else "FLOAT"
    if name in SIMPLE_TYPES:
        return SIMPLE_TYPES[name]
    raise SchemaError(f"unsupported column type db.{name}")


def _column(table, name, call):
    column = {"name": name, "type": None, "pk": False, "null": True, "unique": False, "index": False,
              "default": _NO_DEFAULT, "fk": None}
    for arg in call.args:
        if isinstance(arg, ast.Call) and _is_db(arg.func, "ForeignKey"):
            target = _const(arg.args[0])
            ondelete = next((_const(kw.value) for kw in arg.keywords if kw.arg == "ondelete"), None)
            column["fk"] = (target, ondelete)
        else:
            column["type"] = _sql_type(arg)
    for keyword in call.keywords:
        if keyword.arg == "primary_key":
            column["pk"] = _const(keyword.value)
        elif keyword.arg == "nullable":
            column["null"] = _const(keyword.value)
        elif keyword.arg in ("unique", "index"):
            column[keyword.arg] = _const(keyword.value)
        elif keyword.arg == "default":
            column["default"] = keyword.value
    if column["type"] is None:
        raise SchemaError(f"{table}.{name}: no column type")
    if column["pk"]:
        column["null"] = False
    return column


def _table_args(node):
    """``db.Index(...)`` / ``db.UniqueConstraint(...)`` entries of ``__table_args__``."""
    items = node.elts if isinstance(node, (ast.Tuple, ast.List)) else [node]
    indexes = []
    for item in items:
        if not isinstance(item, ast.Call):
            continue
        columns = [_const(a) for a in item.args if isinstance(a, ast.Constant)]
        if _is_db(item.func, "Index"):
            indexes.append({"name": columns[0], "columns": columns[1:], "unique": False})
        elif _is_db(item.func, "UniqueConstraint"):
            name = next(_const(kw.value) for kw in item.keywords if kw.arg == "name")
            indexes.append({"name": name, "columns": columns, "unique": True})
    return indexes


def parse_models():
    tables = {}
    for path in sorted(MODELS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            name, columns, indexes = None, [], []
            for stmt in cls.body:
                if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                    continue
                target = stmt.targets[0].id
                if target == "__tablename__":
                    name = _const(stmt.value)
                elif target == "__table_args__":
                    indexes = _table_args(stmt.value)
                elif isinstance(stmt.value, ast.Call) and _is_db(stmt.value.func, "Column"):
                    columns.append((target, stmt.value))
            if name is None:
                continue
            doc = (ast.get_docstring(cls) or "").strip().splitlines()
            tables[name] = {"name": name, "class": cls.name, "comment": doc[0] if doc else "",
                            "columns": [_column(name, n, c) for n, c in columns], "indexes": indexes}
    return tables


def validate(tables):
    for table in tables.values():
        names = [c["name"] for c in table["columns"]]
        if len(set(names)) != len(names):
            raise SchemaError(f"{table['name']}: duplicate column names")
        if sum(1 for c in table["columns"] if c["pk"]) != 1:
            raise SchemaError(f"{table['name']}: expected exactly one primary key column")
        for index in table["indexes"]:
            for column in index["columns"]:
                if column not in names:
                    raise SchemaError(f"{table['name']}: index {index['name']} uses unknown column {column}")
        for column in table["columns"]:
            if column["fk"]:
                target_table, _, target_column = column["fk"][0].partition(".")
                target = tables.get(target_table)
                if target is None or target_column not in [c["name"] for c in target["columns"]]:
                    raise SchemaError(f"{table['name']}.{column['name']}: foreign key to unknown {column['fk'][0]}")
                if column["fk"][1] == "SET NULL" and not column["null"]:
                    raise SchemaError(f"{table['name']}.{column['name']}: ON DELETE SET NULL needs a nullable column")
        for identifier in [table["name"]] + [i["name"] for i in table["indexes"]]:
            if len(identifier) > 64:
                raise SchemaError(f"identifier too long for MySQL: {identifier}")


def creation_order(tables):
    """Tables sorted so that every referenced table is created first (self references are fine)."""
    ordered, done = [], set()

    def visit(name, trail=()):
        if name in done:
            return
        if name in trail:
            raise SchemaError("circular foreign keys: " + " -> ".join(trail + (name,)))
        for column in tables[name]["columns"]:
            if column["fk"]:
                target = column["fk"][0].partition(".")[0]
                if target != name:
                    visit(target, trail + (name,))
        done.add(name)
        ordered.append(name)

    for name in tables:
        visit(name)
    return ordered


def _default(column):
    value = column["default"]
    if value is _NO_DEFAULT:
        return ""
    if isinstance(value, ast.Name) and value.id == "utcnow":
        return " DEFAULT (UTC_TIMESTAMP())"
    value = _const(value)
    if isinstance(value, bool):
        return f" DEFAULT {int(value)}"
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    return " DEFAULT '" + str(value).replace("'", "''") + "'"


def render_table(table):
    lines = []
    for column in table["columns"]:
        parts = [f"`{column['name']}`", column["type"]]
        if column["pk"]:
            parts.append("NOT NULL AUTO_INCREMENT")
        else:
            parts.append("NULL" if column["null"] else "NOT NULL")
            parts.append(_default(column).strip())
        lines.append("  " + " ".join(p for p in parts if p))
    primary = next(c["name"] for c in table["columns"] if c["pk"])
    lines.append(f"  PRIMARY KEY (`{primary}`)")
    for column in table["columns"]:
        if column["unique"] and column["index"]:
            lines.append(f"  UNIQUE KEY `ix_{table['name']}_{column['name']}` (`{column['name']}`)")
        elif column["unique"]:
            lines.append(f"  UNIQUE KEY `uq_{table['name']}_{column['name']}` (`{column['name']}`)")
        elif column["index"]:
            lines.append(f"  KEY `ix_{table['name']}_{column['name']}` (`{column['name']}`)")
    for index in table["indexes"]:
        kind = "UNIQUE KEY" if index["unique"] else "KEY"
        lines.append(f"  {kind} `{index['name']}` ({', '.join('`' + c + '`' for c in index['columns'])})")
    for column in table["columns"]:
        if column["fk"]:
            target_table, _, target_column = column["fk"][0].partition(".")
            rule = f" ON DELETE {column['fk'][1]}" if column["fk"][1] else ""
            lines.append(f"  CONSTRAINT `fk_{table['name']}_{column['name']}` FOREIGN KEY (`{column['name']}`) "
                         f"REFERENCES `{target_table}` (`{target_column}`){rule}")
    heading = f"-- {table['name']}" + (f": {table['comment']}" if table["comment"] else "")
    return heading + f"\nCREATE TABLE IF NOT EXISTS `{table['name']}` (\n" + ",\n".join(lines) + \
        "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n"


def build():
    tables = parse_models()
    validate(tables)
    order = creation_order(tables)
    header = (
        "-- PawConnect database schema (MySQL 8.0 or newer, InnoDB, utf8mb4)\n"
        "--\n"
        "-- Generated from the models in app/models by tools/make_schema.py. Do not edit it by hand:\n"
        "-- change a model, then run  python tools/make_schema.py  again.\n"
        "--\n"
        "-- You normally do not need this file: `python init_db.py` creates the same tables and the default\n"
        "-- administrator for you. Use it only if you prefer to create the tables yourself:\n"
        f"--     mysql -u root -p < database/schema.sql\n"
        "-- It creates empty tables only (no accounts) and never drops or changes existing tables.\n"
        f"-- Tables: {len(order)}\n\n"
        f"CREATE DATABASE IF NOT EXISTS `{DATABASE_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
        f"USE `{DATABASE_NAME}`;\n\n"
    )
    return header + "\n".join(render_table(tables[name]) for name in order), order


def main():
    try:
        text, order = build()
    except SchemaError as error:
        print(f"Schema problem: {error}")
        return 1
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print("database/schema.sql is out of date. Run: python tools/make_schema.py")
            return 1
        print(f"database/schema.sql matches the models ({len(order)} tables).")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(order)} tables.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
