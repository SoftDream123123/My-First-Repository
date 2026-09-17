"""架构约束测试（计划书 module-08 §5.3 / §5.4）。

这些约束靠人眼评审最容易随时间流失 —— 一次「就地 import 一下」就能破坏分层，
而功能测试全绿。用测试把它们钉住：

  · ai 不依赖任何业务模块（§5.3-5）
  · core 无对业务模块的顶层导入，只有函数体内延迟导入（§5.3-6）
  · 业务模块之间无反向依赖（§5.4-3）
  · 分层单向：router → service → repository → models（§5.4-2、§5.4-6）
  · 七个独立 package 且各层文件齐备（§5.4-1、§5.4-2）

判定只看**模块级**导入：写在函数体内的延迟导入、以及 `if TYPE_CHECKING:`
块内的类型专用导入都不算运行时依赖 —— 后者正是 core.deps 保持单向的手法。
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

ALL_MODULES = ["core", "auth", "position", "question", "interview", "evaluation", "ai"]
BUSINESS_MODULES = {"auth", "position", "question", "interview", "evaluation"}

LAYERED_MODULES = ["auth", "position", "question", "interview", "evaluation"]
LAYER_FILES = ["models.py", "schemas.py", "repository.py", "service.py", "router.py"]

# 模块 → 其**禁止**依赖的业务模块（计划书 §5.4-3「无反向依赖」）
FORBIDDEN_DEPENDENCIES = {
    "auth": {"position", "question", "interview", "evaluation"},
    "position": {"question", "interview", "evaluation"},
    "question": {"interview", "evaluation"},
    "interview": {"evaluation"},
    "evaluation": {"position", "question"},
}


def _top_level_imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    """顶层（模块级）的 app.* 导入 → [(module, 被导入名元组), ...]。

    只遍历 tree.body，因此函数体内的延迟导入与 if TYPE_CHECKING 块内的
    导入都不会被算作运行时依赖。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, tuple[str, ...]]] = []

    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("app."):
                found.append((node.module, tuple(a.name for a in node.names)))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    found.append((alias.name, ()))

    return found


def _module_deps(path: Path) -> set[str]:
    """该文件顶层依赖的 app 子包名集合，如 {'core', 'position'}。"""
    deps = set()
    for module, _names in _top_level_imports(path):
        parts = module.split(".")
        if len(parts) >= 2:
            deps.add(parts[1])
    return deps


def _own_module_refs(path: Path, module: str) -> set[str]:
    """该文件引用的**同模块内部**子模块/名，如 {'service', 'schemas'}。"""
    refs: set[str] = set()
    for imported_module, names in _top_level_imports(path):
        parts = imported_module.split(".")
        if len(parts) < 2 or parts[1] != module:
            continue
        if len(parts) == 2:
            refs.update(names)  # from app.position import service, schemas
        else:
            refs.add(parts[2])  # from app.position.service import ...
    return refs


# ---------------------------- 包与分层存在性 ----------------------------


def test_seven_modules_exist():
    actual = {p.name for p in APP.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    assert set(ALL_MODULES) <= actual


@pytest.mark.parametrize("module", LAYERED_MODULES)
def test_five_layer_files_exist(module):
    for filename in LAYER_FILES:
        assert (APP / module / filename).exists(), f"{module}/{filename} 缺失"


# ------------------------------ 依赖方向 ------------------------------


@pytest.mark.parametrize("path", sorted((APP / "ai").glob("*.py")), ids=lambda p: p.name)
def test_ai_depends_on_no_business_module(path):
    """§5.3-5：ai 是被调用的能力包，不得反向依赖任何业务模块。"""
    offenders = _module_deps(path) & BUSINESS_MODULES
    assert not offenders, f"ai/{path.name} 依赖了业务模块: {sorted(offenders)}"


@pytest.mark.parametrize("path", sorted((APP / "core").glob("*.py")), ids=lambda p: p.name)
def test_core_has_no_top_level_business_import(path):
    """§5.3-6：core 对业务模块的依赖只能是函数体内延迟导入。"""
    offenders = _module_deps(path) & BUSINESS_MODULES
    assert not offenders, (
        f"core/{path.name} 顶层导入了业务模块: {sorted(offenders)}"
        "（应改为函数体内延迟导入）"
    )


@pytest.mark.parametrize("module,forbidden", sorted(FORBIDDEN_DEPENDENCIES.items()))
def test_no_reverse_dependency(module, forbidden):
    """§5.4-3：不得出现反向依赖（如 position 依赖 interview）。"""
    offenders = set()
    for path in sorted((APP / module).glob("*.py")):
        hits = _module_deps(path) & forbidden
        if hits:
            offenders.add(f"{path.name} → {sorted(hits)}")

    assert not offenders, f"{module} 存在反向依赖: {sorted(offenders)}"


# ------------------------------ 分层职责 ------------------------------


@pytest.mark.parametrize("module", LAYERED_MODULES)
def test_repository_does_not_reach_up(module):
    """§5.4-6：repository 是最底层，不得依赖 service / router。"""
    refs = _own_module_refs(APP / module / "repository.py", module)
    offenders = refs & {"service", "router"}
    assert not offenders, f"{module}/repository.py 依赖了上层: {sorted(offenders)}"


@pytest.mark.parametrize("module", LAYERED_MODULES)
def test_models_is_pure_schema(module):
    """models.py 只承载表结构，不依赖同模块任何其他层。"""
    refs = _own_module_refs(APP / module / "models.py", module)
    assert refs == set(), f"{module}/models.py 不应依赖同模块其他层: {sorted(refs)}"


@pytest.mark.parametrize("module", LAYERED_MODULES)
def test_router_goes_through_service(module):
    """§5.4-4：router 只做校验/鉴权/响应包装，数据访问一律经 service。"""
    refs = _own_module_refs(APP / module / "router.py", module)
    assert "repository" not in refs, f"{module}/router.py 绕过 service 直接用了 repository"


@pytest.mark.parametrize("module", LAYERED_MODULES)
def test_service_uses_repository_not_raw_sql(module):
    """§5.4-5：service 只调 repository，不直接执行 SQL。"""
    source = (APP / module / "service.py").read_text(encoding="utf-8")
    assert "session.execute" not in source
    assert "db.execute" not in source, f"{module}/service.py 直接执行了 SQL"
