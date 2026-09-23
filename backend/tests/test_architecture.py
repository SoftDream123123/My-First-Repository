"""架构约束测试（计划书 module-08 §5.3 / §5.4）。

这些约束靠人眼评审最容易随时间流失 —— 一次「就地 import 一下」就能破坏分层，
而功能测试全绿。用测试把它们钉住：

  · ai 不依赖任何业务模块（§5.3-5）
  · core 无对业务模块的顶层导入，只有函数体内延迟导入（§5.3-6）
  · 业务模块之间无反向依赖（§5.4-3）
  · 分层单向：router → service → repository → models（§5.4-2、§5.4-6）
  · 十个独立 package 且各层文件齐备（§5.4-1、§5.4-2）

判定只看**模块级**导入：写在函数体内的延迟导入、以及 `if TYPE_CHECKING:`
块内的类型专用导入都不算运行时依赖 —— 后者正是 core.deps 保持单向的手法。
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

ALL_MODULES = [
    "core",
    "auth",
    "position",
    "question",
    "interview",
    "evaluation",
    "ai",
    "practice",
    "resume",
    "sms",
]
BUSINESS_MODULES = {
    "auth",
    "position",
    "question",
    "interview",
    "evaluation",
    "practice",
    "resume",
}

LAYERED_MODULES = [
    "auth",
    "position",
    "question",
    "interview",
    "evaluation",
    "practice",
    "resume",
]
LAYER_FILES = ["models.py", "schemas.py", "repository.py", "service.py", "router.py"]

# 模块 → 其**禁止**依赖的业务模块（计划书 §5.4-3「无反向依赖」）
#
# 注意：interview / practice 的禁止集合**不含** resume —— 它们各自单向依赖
# resume（HR 读简历 + 分类补题 / 刷题推荐）是允许的。resume 则不得反向依赖
# 任何业务模块，否则会把 practice ↔ interview 的循环引进来（PRD §9）。
FORBIDDEN_DEPENDENCIES = {
    "auth": {"position", "question", "interview", "evaluation", "practice", "resume"},
    "position": {"question", "interview", "evaluation", "practice", "resume"},
    "question": {"interview", "evaluation", "practice", "resume"},
    "interview": {"evaluation", "practice"},
    "evaluation": {"position", "question", "practice", "resume"},
    # practice 与真实面试**完全解耦**：刷题是另一条业务线，
    # 既不读 interview 的数据，也不该被 interview 反向依赖。
    "practice": {"interview", "position", "evaluation"},
    # resume 是「被依赖但不依赖」的节点：删除保护交给外键 RESTRICT，
    # 因此零业务模块依赖、零跨表查询。允许依赖 core / auth（归属校验用
    # auth 的 ensure_owner_match），但不得依赖任何业务模块。
    "resume": {"position", "question", "interview", "evaluation", "practice"},
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


def test_ten_modules_exist():
    """十个独立 package 齐备。

    `len(ALL_MODULES) == 10` 是**防漏登记**的断言：只写 `<=` 时，新增包却忘了
    登记进本文件，会表现为「这个包的分层与依赖方向不受任何测试保护」，
    而全部用例依然全绿 —— 这是最容易被忽视的一类失效。

    测试名随包数演进（8 → 9 → 10），与本项目既有的
    `test_eight_modules_exist` → `test_nine_modules_exist` 同款处理：
    名字里的数字过期比改名字本身更有害 —— 一个叫 `test_nine_modules_exist`
    却断言 10 的用例，会让读的人先怀疑自己看错了。
    """
    actual = {p.name for p in APP.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    assert set(ALL_MODULES) <= actual
    assert len(ALL_MODULES) == 10


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


@pytest.mark.parametrize("path", sorted((APP / "sms").glob("*.py")), ids=lambda p: p.name)
def test_sms_depends_on_no_business_module(path):
    """与 ai 同规：sms 是基础设施，不得反向依赖任何业务模块（§3.3、§6）。

    它只被 auth 单向依赖，且**不依赖 auth** —— 它不感知验证码的业务语义，
    只负责「把一个字符串发到某个手机号」。这条用例是给新包配的同一道闸门：
    `ai` 有这个保护而 `sms` 没有的话，往 sms 里 import auth 不会被任何测试拦住。
    """
    offenders = _module_deps(path) & BUSINESS_MODULES
    assert not offenders, f"sms/{path.name} 依赖了业务模块: {sorted(offenders)}"


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
