#!/usr/bin/env python3
"""把原型打成单文件 standalone.html。

为什么要这个脚本：ES 模块在 file:// 协议下会被浏览器的 CORS 策略拒绝加载 ——
双击 index.html 就是一片空白。单文件版本没有 import，因而不受该限制。

实现的是一个极小打包器：把
    import { a } from './x.js'   ->  const { a } = __require('./x.js')
    export function f() {...}    ->  function f() {...}  +  exports.f = f
再把每个模块包进独立作用域，避免 render / destroy 这类同名导出互相覆盖。

用法：
    python tools/build-standalone.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
ENTRY = "./main.js"

IMPORT_RE = re.compile(
    r"import\s+(\{[^}]*\}|\*\s+as\s+\w+)\s+from\s+'([^']+)';"
)
EXPORT_DECL_RE = re.compile(
    r"^export\s+((?:async\s+)?function|const|let|var|class)\s+(\w+)", re.M
)
EXPORT_LIST_RE = re.compile(r"^export\s*\{([^}]*)\};?[ \t]*$", re.M)


def module_id(path: Path) -> str:
    """把文件路径转成模块 id（相对 src/ 的 posix 路径，以 ./ 开头）。"""
    return "./" + path.relative_to(SRC).as_posix()


def resolve(base: Path, spec: str) -> Path:
    return (base.parent / spec).resolve()


def transform(path: Path, text: str) -> tuple[str, list[str]]:
    """把一个模块转成注册表函数体，返回 (代码, 导出名列表)。"""
    exported: list[str] = []

    def strip_decl(match: re.Match) -> str:
        kind, name = match.group(1), match.group(2)
        exported.append(name)
        return f"{kind} {name}"

    text = EXPORT_DECL_RE.sub(strip_decl, text)

    def strip_list(match: re.Match) -> str:
        for name in match.group(1).split(","):
            name = name.strip()
            if name:
                exported.append(name)
        return ""

    text = EXPORT_LIST_RE.sub(strip_list, text)

    def rewrite_import(match: re.Match) -> str:
        clause, spec = match.group(1), match.group(2)
        target = resolve(path, spec)
        if not target.exists():
            raise SystemExit(f"{path}: 找不到依赖 {spec}")

        # 两种导入形态要生成不同的绑定：
        #   import { a, b } from  ->  const { a, b } = __require(...)
        #   import * as ns  from  ->  const ns = __require(...)
        if clause.lstrip().startswith("*"):
            name = clause.split("as", 1)[1].strip()
            binding = f"const {name}"
        else:
            binding = f"const {clause}"

        return f"{binding} = __require('{module_id(target)}');"

    text = IMPORT_RE.sub(rewrite_import, text)

    # 残留检查：漏掉任何一种写法都会产出语法错误的单文件，
    # 与其等到浏览器报错，不如在构建时就失败。
    if re.search(r"^\s*import\s", text, re.M):
        raise SystemExit(f"{path}: 存在未能识别的 import 写法，请检查")
    if re.search(r"^\s*export\s", text, re.M):
        raise SystemExit(f"{path}: 存在未能识别的 export 写法，请检查")

    tail = "".join(f"exports.{name} = {name};\n" for name in exported)

    # 注意：tail 必须拼回去。漏了它不会报语法错误，
    # 只会让所有模块的导出为空 —— 表现为运行时的 "undefined" 报错。
    return f"{text}\n{tail}", exported


def collect(entry: Path) -> list[Path]:
    """从入口出发做深度优先遍历，返回按依赖优先顺序排列的模块。"""
    ordered: list[Path] = []
    seen: set[Path] = set()

    def visit(path: Path) -> None:
        if path in seen:
            return
        seen.add(path)
        text = path.read_text(encoding="utf-8")
        for _clause, spec in IMPORT_RE.findall(text):
            visit(resolve(path, spec))
        ordered.append(path)

    visit(entry)
    return ordered


def build() -> Path:
    modules = collect(SRC / "main.js")

    chunks = []
    for path in modules:
        source = path.read_text(encoding="utf-8")
        code, _ = transform(path, source)
        indented = "\n".join(("  " + line) if line.strip() else "" for line in code.splitlines())
        chunks.append(f"__modules['{module_id(path)}'] = function (exports, __require) {{\n{indented}\n}};\n")

    registry = "\n".join(chunks)

    # 自检：导出赋值缺失不会造成语法错误，只会让页面在运行时读到 undefined。
    # 这里直接拦下来。
    if registry.count("exports.") < 20:
        raise SystemExit(
            f"打包结果异常：只找到 {registry.count('exports.')} 处导出赋值，"
            "疑似 transform 未把 tail 拼回模块体"
        )

    css = "\n".join(
        f"/* ===== {name} ===== */\n{(SRC / 'styles' / name).read_text(encoding='utf-8')}"
        for name in ("tokens.css", "base.css", "components.css", "pages.css")
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1280">
<title>面试助手 · HR 工作台</title>
<!--
  单文件版本 —— 由 tools/build-standalone.py 生成，请勿直接编辑。
  双击即可打开：它不含 ES 模块，因此不受 file:// 的 CORS 限制。
  源码在 src/，改完源码后重新运行构建脚本。
-->
<style>
{css}
</style>
</head>
<body>
<div id="app"></div>
<script>
(function () {{
  "use strict";
  var __modules = {{}};
  var __cache = {{}};
  function __require(id) {{
    if (__cache[id]) return __cache[id];
    var exports = {{}};
    __cache[id] = exports;
    __modules[id](exports, __require);
    return exports;
  }}

{registry}
  __require('{ENTRY}');
}})();
</script>
</body>
</html>
"""

    out = ROOT / "standalone.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    out = build()
    size = out.stat().st_size
    print(f"[OK] 已生成 {out.name}（{size / 1024:.1f} KB）")
    print("     双击即可打开，无需本地服务器。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
