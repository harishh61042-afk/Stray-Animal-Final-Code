#!/usr/bin/env python3
"""Static consistency checker for PawConnect.

Needs only Python 3 and Jinja2 (it never imports Flask extensions or the database), so it can run anywhere:

    python tools/check_project.py            # whole project
    python tools/check_project.py --quiet    # only print problems

What it verifies
  * every .py file compiles, every Jinja template parses
  * blueprints / routes: each ``url_for`` / ``link_for`` / ``redirect`` target exists and gets its URL arguments
  * every ``render_template`` / extends / include / import target exists, every macro / filter used is defined
  * ``url_for('static', filename=...)`` points to a real file
  * every POST <form> in a template carries a CSRF token
  * ``@bp.route`` is the outermost decorator and non-public routes require sign-in / a role
  * model attributes used in queries / constructors exist; constants / service functions exist and calls match
    the function signature (names + number of arguments)
Exit status is 1 when a problem is found.
"""
import ast
import py_compile
import re
import sys
from pathlib import Path

from jinja2 import Environment, nodes
from jinja2 import filters as jinja_filters
from jinja2 import tests as jinja_tests

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
TEMPLATES = APP / "templates"
STATIC = APP / "static"
ROUTES = APP / "routes"
QUIET = "--quiet" in sys.argv

errors, warnings = [], []


def err(message):
    errors.append(message)


def warn(message):
    warnings.append(message)


def rel(path):
    return str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")


def const(node):
    return node.value if isinstance(node, ast.Constant) else None


# --------------------------------------------------------------------- python
def python_files():
    skip = {".venv", "venv", "__pycache__", ".git", "node_modules"}
    return [p for p in ROOT.rglob("*.py") if not skip.intersection(p.relative_to(ROOT).parts)]


def check_compile():
    for path in python_files():
        try:
            py_compile.compile(str(path), doraise=True, cfile=str(Path("/tmp") / "pc_check.pyc") if Path("/tmp").exists() else None)
        except py_compile.PyCompileError as exc:
            err(f"{rel(path)}: syntax error: {exc.msg.strip()}")


# ----------------------------------------------------------------- templates
ENV = Environment(extensions=["jinja2.ext.do"])
TEMPLATE_AST = {}


def load_templates():
    for path in sorted(TEMPLATES.rglob("*.html")):
        name = path.relative_to(TEMPLATES).as_posix()
        try:
            TEMPLATE_AST[name] = ENV.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            err(f"template {name}: {type(exc).__name__}: {exc}")


def custom_filters():
    names = set()
    text = (APP / "template_utils.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if "add_template_filter" in line:
            match = re.search(r'"(\w+)"\)\s*$', line.strip())
            if match:
                names.add(match.group(1))
    return names


def global_names():
    names = {"range", "dict", "lipsum", "cycler", "joiner", "namespace", "url_for", "get_flashed_messages", "request",
             "session", "g", "config", "csrf_token", "current_user", "caller", "varargs", "kwargs", "loop", "self",
             "true", "false", "none", "True", "False", "None", "super"}
    text = (APP / "template_utils.py").read_text(encoding="utf-8")
    names.update(re.findall(r"^\s{8}(\w+)=", text, re.M))                # jinja_env.globals.update(name=...)
    names.update(re.findall(r'^\s{12}"(\w+)":', text, re.M))             # context processor keys
    return names


def module_names(path):
    """Top-level names defined by a python module (functions, classes, assignments, imports)."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
    return names


def check_templates(route_table):
    builtin_filters = set(jinja_filters.FILTERS) | {"tojson"} | custom_filters()
    builtin_tests = set(jinja_tests.TESTS)
    known_globals = global_names()
    constants_names = module_names(APP / "constants.py")
    rules_names = module_names(APP / "services" / "rules.py")
    macro_cache = {}

    def macros_of(template_name):
        if template_name not in macro_cache:
            tree = TEMPLATE_AST.get(template_name)
            macro_cache[template_name] = {m.name for m in tree.find_all(nodes.Macro)} if tree else set()
        return macro_cache[template_name]

    for name, tree in TEMPLATE_AST.items():
        aliases = {}
        local_names = set()
        for node in tree.find_all((nodes.Extends, nodes.Include, nodes.Import, nodes.FromImport)):
            target = node.template
            if isinstance(target, nodes.Const):
                if target.value not in TEMPLATE_AST:
                    err(f"template {name}: refers to missing template '{target.value}'")
                elif isinstance(node, nodes.Import):
                    aliases[node.target] = target.value
                elif isinstance(node, nodes.FromImport):
                    for item in node.names:
                        wanted, alias = item if isinstance(item, tuple) else (item, item)
                        local_names.add(alias)
                        if wanted not in macros_of(target.value) and not wanted.startswith("_"):
                            err(f"template {name}: '{wanted}' is not a macro of {target.value}")
            if isinstance(node, nodes.Import):
                local_names.add(node.target)
        for node in tree.find_all(nodes.Macro):
            local_names.add(node.name)
        for node in tree.find_all(nodes.Name):
            if node.ctx in ("store", "param"):
                local_names.add(node.name)

        for node in tree.find_all(nodes.Filter):
            if node.name not in builtin_filters:
                err(f"template {name}: unknown filter '{node.name}'")
        for node in tree.find_all(nodes.Test):
            if node.name not in builtin_tests:
                err(f"template {name}: unknown test '{node.name}'")

        for call in tree.find_all(nodes.Call):
            func = call.node
            if isinstance(func, nodes.Getattr) and isinstance(func.node, nodes.Name):
                owner = func.node.name
                if owner in aliases and func.attr not in macros_of(aliases[owner]):
                    err(f"template {name}: macro '{owner}.{func.attr}' does not exist in {aliases[owner]}")
                if owner == "rules" and func.attr not in rules_names:
                    err(f"template {name}: rules.{func.attr} does not exist")
            elif isinstance(func, nodes.Name):
                if func.name not in local_names and func.name not in known_globals:
                    err(f"template {name}: call to unknown function/macro '{func.name}'")
        for node in tree.find_all(nodes.Getattr):
            if isinstance(node.node, nodes.Name) and node.node.name == "C" and node.attr not in constants_names:
                err(f"template {name}: constant C.{node.attr} does not exist")

        for call in tree.find_all(nodes.Call):
            if isinstance(call.node, nodes.Name) and call.node.name == "url_for" and call.args:
                first = call.args[0]
                if not isinstance(first, nodes.Const):
                    continue
                keys = {kw.key for kw in call.kwargs}
                check_url_for(f"template {name}", first.value, keys, bool(call.dyn_kwargs or call.dyn_args), route_table, None)
                if first.value == "static":
                    for kw in call.kwargs:
                        if kw.key == "filename" and isinstance(kw.value, nodes.Const) and not (STATIC / kw.value.value).exists():
                            err(f"template {name}: static file '{kw.value.value}' does not exist")

    check_csrf()


def check_csrf():
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = re.sub(r"\{#.*?#\}", "", path.read_text(encoding="utf-8"), flags=re.S)
        for match in re.finditer(r"<form\b[^>]*>", text, re.I):
            tag = match.group(0)
            if not re.search(r"method\s*=\s*[\"']post[\"']", tag, re.I):
                continue
            end = text.find("</form>", match.end())
            body = text[match.end(): end if end != -1 else len(text)]
            if not re.search(r"csrf_token|hidden_tag|ui\.csrf|\bcsrf\(\)", body):
                err(f"template {path.relative_to(TEMPLATES).as_posix()}: POST form without CSRF token near '{tag[:70]}'")
            if 'type="file"' in body.replace("'", '"') and "multipart/form-data" not in tag:
                err(f"template {path.relative_to(TEMPLATES).as_posix()}: form with file input needs enctype=\"multipart/form-data\"")


# --------------------------------------------------------------------- routes
AUTH_DECORATORS = {"login_required", "roles_required", "admin_required", "approved_volunteer_required"}
PUBLIC_ENDPOINTS = {
    "public.home", "public.about", "public.how_it_works", "public.animals", "public.animal_detail", "public.contact",
    "auth.login", "auth.register", "auth.register_volunteer",
    "reports.new", "reports.submitted", "reports.track", "files.uploaded",
    "shelters.directory", "shelters.detail",
}


def decorator_name(dec):
    node = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def discover_routes():
    table = {}
    if not ROUTES.exists():
        return table
    for path in sorted(ROUTES.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bp_name = bp_var = None
        prefix = ""
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and decorator_name(node.value) == "Blueprint":
                bp_name = const(node.value.args[0]) if node.value.args else None
                bp_var = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
                for kw in node.value.keywords:
                    if kw.arg == "url_prefix":
                        prefix = const(kw.value) or ""
        if not bp_name or bp_var != "bp":
            err(f"{rel(path)}: must define ``bp = Blueprint(...)``")
            continue
        if bp_name != path.stem:
            err(f"{rel(path)}: blueprint name '{bp_name}' must equal the module name '{path.stem}'")
        for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            route_positions, other_positions = [], []
            for index, dec in enumerate(func.decorator_list):
                is_route = (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                            and dec.func.attr in ("route", "get", "post")
                            and isinstance(dec.func.value, ast.Name) and dec.func.value.id == bp_var)
                (route_positions if is_route else other_positions).append(index)
            if not route_positions:
                continue
            if other_positions and min(other_positions) < max(route_positions):
                err(f"{rel(path)}:{func.lineno}: in '{func.name}' @bp.route must be the FIRST (outermost) decorator, "
                    f"otherwise the permission decorator is bypassed")
            names = {decorator_name(func.decorator_list[i]) for i in other_positions}
            for index in route_positions:
                dec = func.decorator_list[index]
                rule = const(dec.args[0]) if dec.args else None
                if rule is None:
                    err(f"{rel(path)}:{func.lineno}: route without a literal URL")
                    continue
                endpoint = func.name
                methods = {"GET"} if dec.func.attr == "route" else {dec.func.attr.upper()}
                defaults = set()
                for kw in dec.keywords:
                    if kw.arg == "endpoint":
                        endpoint = const(kw.value) or endpoint
                    elif kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                        methods = {const(e) for e in kw.value.elts}
                    elif kw.arg == "defaults" and isinstance(kw.value, ast.Dict):
                        defaults = {const(k) for k in kw.value.keys}
                args = set(re.findall(r"<(?:[^<>:]+:)?(\w+)>", rule)) - defaults
                full = f"{bp_name}.{endpoint}"
                info = table.setdefault(full, {"rules": [], "args": [], "methods": set(), "file": rel(path), "line": func.lineno})
                info["rules"].append(prefix + rule)
                info["args"].append(args)
                info["methods"] |= methods
                if full not in PUBLIC_ENDPOINTS and not (AUTH_DECORATORS & names):
                    err(f"{rel(path)}:{func.lineno}: route '{full}' has no login_required / roles_required decorator")
                if "POST" in methods and "GET" not in methods and full == "auth.login":
                    err(f"{rel(path)}: auth.login must also accept GET")
    return table


def check_url_for(where, endpoint, keys, dynamic, route_table, current_bp):
    if endpoint == "static":
        return
    if endpoint.startswith(".") and current_bp:
        endpoint = current_bp + endpoint
    info = route_table.get(endpoint)
    if info is None:
        err(f"{where}: url_for/link_for target '{endpoint}' is not a defined route")
        return
    if dynamic:
        return
    required = set.intersection(*info["args"]) if info["args"] else set()
    missing = required - keys
    if missing:
        err(f"{where}: '{endpoint}' needs URL argument(s) {sorted(missing)}")


# ------------------------------------------------------------------- models
MODEL_ALLOWED = {"query", "metadata", "__tablename__", "__table__", "id", "is_authenticated", "is_anonymous", "get_id",
                 "is_active", "registry", "__mapper__", "__name__"}


def load_models():
    models = {}
    pending_backrefs = []
    for path in sorted((APP / "models").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            bases = {ast.unparse(b) for b in cls.bases}
            if not any("Model" in b for b in bases):
                continue
            attrs = set(MODEL_ALLOWED)
            for node in cls.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    attrs.add(node.name)
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            attrs.add(target.id)
                    value = node.value
                    if isinstance(value, ast.Call) and decorator_name(value) == "relationship":
                        target_cls = const(value.args[0]) if value.args else None
                        for kw in value.keywords:
                            if kw.arg == "backref":
                                if const(kw.value):
                                    pending_backrefs.append((target_cls, const(kw.value)))
                                elif isinstance(kw.value, ast.Call) and kw.value.args:
                                    pending_backrefs.append((target_cls, const(kw.value.args[0])))
            models[cls.name] = attrs
    for target_cls, name in pending_backrefs:
        if target_cls in models and name:
            models[target_cls].add(name)
    return models


# ------------------------------------------------------------ python usage
def internal_module_file(dotted):
    parts = dotted.split(".")
    base = ROOT.joinpath(*parts)
    if base.with_suffix(".py").exists():
        return base.with_suffix(".py")
    if (base / "__init__.py").exists():
        return base / "__init__.py"
    return None


def function_defs(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def check_signature(where, call, func):
    args = func.args
    positional = [a.arg for a in args.posonlyargs + args.args]
    kwonly = [a.arg for a in args.kwonlyargs]
    defaults_count = len(args.defaults)
    required = set(positional[: len(positional) - defaults_count]) | {a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is None}
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return
    if len(call.args) > len(positional) and not args.vararg:
        err(f"{where}: {func.name}() takes at most {len(positional)} positional argument(s), {len(call.args)} given")
        return
    given = set(positional[: len(call.args)])
    for kw in call.keywords:
        if kw.arg not in positional + kwonly and not args.kwarg:
            err(f"{where}: {func.name}() has no parameter '{kw.arg}'")
        given.add(kw.arg)
    missing = required - given
    if missing:
        err(f"{where}: {func.name}() missing argument(s) {sorted(missing)}")


def check_python_usage(route_table, models):
    constants_names = module_names(APP / "constants.py")
    for path in python_files():
        if "tests" in path.relative_to(ROOT).parts or path.name == "check_project.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        current_bp = path.stem if path.parent == ROUTES else None
        module_alias = {}      # alias -> module file
        func_alias = {}        # imported function name -> (file, name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and (node.module == "app" or node.module.startswith("app.")):
                parent = internal_module_file(node.module)
                for alias in node.names:
                    local = alias.asname or alias.name
                    sub = internal_module_file(f"{node.module}.{alias.name}")
                    if sub is not None:
                        module_alias[local] = sub
                    elif parent is not None:
                        if alias.name not in module_names(parent) and alias.name != "*":
                            err(f"{rel(path)}:{node.lineno}: cannot import '{alias.name}' from {node.module}")
                        else:
                            func_alias[local] = (parent, alias.name)
        for node in ast.walk(tree):
            where = f"{rel(path)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Call):
                name = decorator_name(node)
                if name in ("url_for", "link_for") and node.args and const(node.args[0]) is not None:
                    keys = {k.arg for k in node.keywords if k.arg}
                    dynamic = any(k.arg is None for k in node.keywords)
                    if name == "url_for" and const(node.args[0]) == "static":
                        continue
                    check_url_for(where, const(node.args[0]), keys, dynamic, route_table, current_bp)
                elif name == "render_template" and node.args and isinstance(const(node.args[0]), str):
                    if const(node.args[0]) not in TEMPLATE_AST:
                        err(f"{where}: render_template('{const(node.args[0])}') - template does not exist")
                # model constructor / filter_by keywords
                if isinstance(node.func, ast.Name) and node.func.id in models:
                    for kw in node.keywords:
                        if kw.arg and kw.arg not in models[node.func.id]:
                            err(f"{where}: {node.func.id}({kw.arg}=...) - model has no such column/attribute")
                if (isinstance(node.func, ast.Attribute) and node.func.attr == "filter_by"
                        and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "query"
                        and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id in models):
                    cls = node.func.value.value.id
                    for kw in node.keywords:
                        if kw.arg and kw.arg not in models[cls]:
                            err(f"{where}: {cls}.query.filter_by({kw.arg}=...) - model has no such column")
                # calls into internal modules: existence + signature
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id in module_alias:
                    target = module_alias[node.func.value.id]
                    if target.name != "constants.py":
                        defs = function_defs(target)
                        if node.func.attr in defs:
                            check_signature(where, node, defs[node.func.attr])
                        elif node.func.attr not in module_names(target):
                            err(f"{where}: {rel(target)} has no function '{node.func.attr}'")
                elif isinstance(node.func, ast.Name) and node.func.id in func_alias:
                    target, original = func_alias[node.func.id]
                    defs = function_defs(target)
                    if original in defs:
                        check_signature(where, node, defs[original])
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                base = node.value.id
                if base in models and node.attr not in models[base] and not node.attr.startswith("__"):
                    err(f"{where}: {base}.{node.attr} - model has no such attribute")
                elif base in module_alias and module_alias[base].name == "constants.py" and node.attr not in constants_names:
                    err(f"{where}: constants.{node.attr} does not exist")
                elif base in module_alias and module_alias[base].name != "constants.py" and not isinstance(getattr(node, "ctx", None), ast.Store):
                    if node.attr not in module_names(module_alias[base]):
                        err(f"{where}: {rel(module_alias[base])} has no attribute '{node.attr}'")


def check_blueprint_registry():
    text = (ROUTES / "__init__.py").read_text(encoding="utf-8")
    listed = re.findall(r'"(\w+)"', text.split("BLUEPRINT_MODULES", 1)[1].split(")", 1)[0])
    for name in listed:
        if not (ROUTES / f"{name}.py").exists():
            err(f"app/routes/{name}.py is listed in BLUEPRINT_MODULES but does not exist")


def check_navigation(route_table):
    sys.path.insert(0, str(ROOT))
    try:
        from app import navigation  # pure python (only imports app.constants)
    except Exception as exc:  # noqa: BLE001
        err(f"navigation.py cannot be imported: {exc}")
        return
    for endpoint in sorted(navigation.all_nav_endpoints()):
        if endpoint not in route_table:
            err(f"navigation.py: endpoint '{endpoint}' is not a defined route")


def main():
    check_compile()
    load_templates()
    check_blueprint_registry()
    route_table = discover_routes()
    models = load_models()
    check_templates(route_table)
    check_python_usage(route_table, models)
    check_navigation(route_table)

    if not QUIET:
        print(f"Checked {len(python_files())} python files, {len(TEMPLATE_AST)} templates, {len(route_table)} endpoints, {len(models)} models.")
    for line in warnings:
        print("warning:", line)
    for line in sorted(set(errors)):
        print("ERROR:  ", line)
    if errors:
        print(f"\n{len(set(errors))} problem(s) found.")
        return 1
    print("No problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
