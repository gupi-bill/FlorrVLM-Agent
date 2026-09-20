#!/usr/bin/env python3
"""S2 · 静态依赖与接口审计工具（离线、零外部依赖）

产出：
  devplan/AUDIT.md        —— 人读的审计报告（依赖表 / 缺失符号 / 占位 / 风险分级）
  devplan/audit_data.json —— 机器可读的中间数据，供后续阶段（S13 门禁）复用

用法：
  python tools/static_audit.py                 # 全量审计并写 AUDIT.md
  python tools/static_audit.py --json-only     # 只刷新 audit_data.json

设计约束（本机环境）：
  * 不导入任何第三方重量包，纯 ast + 标准库；
  * 导入探针在独立子进程中执行并带超时，避免模块顶层副作用拖死审计；
  * 对 GUI / 硬件 / 视觉类可选依赖注入 stub，使导入测试能反映"业务代码是否自洽"
    而非"本机是否装了 pyautogui"。
"""

from __future__ import annotations

import argparse
import ast
import json
import multiprocessing as mp
import os
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".buildozer",
    ".gradle",
    "build",
    "dist",
    ".trae",
    ".trae-html-share-packages",
    ".workbuddy",
    "knowledge_md",
}

# 本机（headless / 无 X server / 无密钥 / 磁盘紧张）允许缺失的可选依赖。
# 审计时会被注入 stub，使导入测试聚焦"代码自洽性"。
OPTIONAL_STUBS = {
    "pyautogui": "GUI 自动化（无 X server）",
    "pynput": "键鼠监听（无 X server）",
    "cv2": "OpenCV（磁盘受限，刻意不装）",
    "numpy": "数值计算",
    "PIL": "Pillow 图像",
    "mss": "屏幕截图",
    "dxcam": "DXGI 截图（Windows）",
    "ultralytics": "YOLO 模型（无权重文件）",
    "torch": "深度学习（磁盘受限）",
    "PyQt5": "Qt 前端",
    "PySide6": "Qt 前端",
    "streamlit": "Streamlit 前端",
    "tkinter": "Tk 前端",
    "win32gui": "Windows 窗口枚举",
    "win32con": "Windows 常量",
    "win32api": "Windows API",
    "openai": "LLM SDK（无密钥）",
    "anthropic": "LLM SDK（无密钥）",
    "google": "Gemini SDK（无密钥）",
    "dotenv": "环境变量加载",
}

STDLIB = set(getattr(sys, "stdlib_module_names", ()))


# --------------------------------------------------------------------------- #
# 1. 收集源文件
# --------------------------------------------------------------------------- #
def iter_py_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def mod_name_of(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


# --------------------------------------------------------------------------- #
# 2. AST 解析
# --------------------------------------------------------------------------- #
class ModuleInfo:
    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self.imports: list[dict] = []        # {kind, module, names, level, line, stubbed}
        self.local_refs: list[dict] = []     # 跨本地模块引用
        self.defs: dict[str, dict] = {}      # 顶层导出符号 -> {kind, args, line}
        self.class_methods: dict[str, dict] = {}
        self.placeholders: list[dict] = []
        self.markers: list[dict] = []        # TODO / FIXME
        self.calls: list[dict] = []          # 对本地符号的调用点
        self.attr_refs: list[dict] = []      # 模块别名上的属性访问 X.attr
        self.aliases: dict[str, str] = {}    # 别名 -> 本地模块名
        self.loc = 0
        self.syntax_error: str | None = None


def parse_module(path: Path, name: str) -> ModuleInfo:
    info = ModuleInfo(name, path)
    src = path.read_text(encoding="utf-8", errors="replace")
    info.loc = len(src.splitlines())
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - 阻断级，极少发生
        info.syntax_error = f"{type(exc).__name__}: {exc.msg} (line {exc.lineno})"
        return info

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                info.imports.append(
                    {"kind": "import", "module": alias.name, "names": [alias.name],
                     "level": 0, "line": node.lineno}
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            info.imports.append(
                {"kind": "from", "module": mod, "names": [a.name for a in node.names],
                 "level": node.level or 0, "line": node.lineno}
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.defs[node.name] = {
                "kind": "async def" if isinstance(node, ast.AsyncFunctionDef) else "def",
                "args": arg_names(node.args),
                "line": node.lineno,
                "decorators": [ast.unparse(d) for d in node.decorator_list],
            }
        elif isinstance(node, ast.ClassDef):
            info.defs[node.name] = {
                "kind": "class", "args": [], "line": node.lineno,
                "decorators": [ast.unparse(d) for d in node.decorator_list],
            }
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    key = f"{node.name}.{sub.name}"
                    info.class_methods[key] = {
                        "kind": "method", "args": arg_names(sub.args), "line": sub.lineno,
                    }
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    info.defs[tgt.id] = {"kind": "const", "args": [], "line": node.lineno,
                                         "decorators": []}

    # 嵌套 import（函数内延迟导入）也纳入依赖图
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and node not in tree.body:
            for alias in node.names:
                info.imports.append(
                    {"kind": "import(deferred)", "module": alias.name,
                     "names": [alias.name], "level": 0, "line": node.lineno}
                )
        elif isinstance(node, ast.ImportFrom) and node not in tree.body:
            info.imports.append(
                {"kind": "from(deferred)", "module": node.module or "",
                 "names": [a.name for a in node.names], "level": node.level or 0,
                 "line": node.lineno}
            )

    collect_calls(tree, info)
    collect_placeholders(tree, src, info)
    build_aliases(info)
    collect_attrs(tree, info)
    return info


def build_aliases(info: ModuleInfo) -> None:
    for imp in info.imports:
        mod = imp["module"]
        if not mod:
            continue
        if imp["kind"].startswith("import"):
            # import a.b.c  ->  可用名是 a
            info.aliases[mod.split(".")[0]] = mod.split(".")[0]
        else:
            for n in imp["names"]:
                if n == "*":
                    continue
                info.aliases[n] = f"{mod}.{n}" if mod else n


def collect_attrs(tree: ast.AST, info: ModuleInfo) -> None:
    """收集 `别名.attr` 形式的引用，用于检测"引用了不存在的模块级符号"。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id
            info.attr_refs.append({"base": base, "attr": node.attr, "line": node.lineno})


def arg_names(a: ast.arguments) -> list[str]:
    out = [x.arg for x in list(a.posonlyargs) + list(a.args)]
    if a.vararg:
        out.append("*" + a.vararg.arg)
    out += [x.arg for x in a.kwonlyargs]
    if a.kwarg:
        out.append("**" + a.kwarg.arg)
    return out


def collect_calls(tree: ast.AST, info: ModuleInfo) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name):
            info.calls.append({
                "target": fn.id, "qual": None, "line": node.lineno,
                "kwargs": [k.arg for k in node.keywords if k.arg],
                "nargs": len(node.args),
            })
        elif isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
            info.calls.append({
                "target": fn.attr, "qual": fn.value.id, "line": node.lineno,
                "kwargs": [k.arg for k in node.keywords if k.arg],
                "nargs": len(node.args),
            })


def collect_placeholders(tree: ast.AST, src: str, info: ModuleInfo) -> None:
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Name) \
                and node.exc.id in {"NotImplementedError", "NotImplemented"}:
            info.placeholders.append({"type": "NotImplementedError", "line": node.lineno,
                                      "text": "raise NotImplementedError"})
        elif isinstance(node, ast.Pass):
            info.placeholders.append({"type": "pass", "line": node.lineno,
                                      "text": lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""})

    for i, line in enumerate(lines, 1):
        up = line
        for marker in ("TODO", "FIXME", "XXX", "HACK"):
            if marker in up:
                info.markers.append({"type": marker, "line": i, "text": up.strip()[:160]})
                break


# --------------------------------------------------------------------------- #
# 3. 导入探针（子进程 + 超时 + stub 注入）
# --------------------------------------------------------------------------- #
PROBE_SRC = r'''
import sys, types, importlib, json, traceback, os

STUBS = json.loads(sys.argv[1])
MOD = sys.argv[2]
ROOT = sys.argv[3]
sys.path.insert(0, ROOT)

class _Stub(types.ModuleType):
    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []
    def __getattr__(self, item):
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        m = _Stub(self.__name__ + "." + item)
        sys.modules[self.__name__ + "." + item] = m
        return m
    def __call__(self, *a, **k):
        # st.columns(3) 之类需要可解包的返回值：单整数实参时返回 stub 列表
        if len(a) == 1 and isinstance(a[0], int) and a[0] > 0:
            return [_Stub(self.__name__ + f"()[{i}]") for i in range(a[0])]
        return _Stub(self.__name__ + "()")
    def __contains__(self, item):
        return False
    def __iter__(self):
        return iter(())
    def __bool__(self):
        return False
    def __len__(self):
        return 0
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False

for name in STUBS:
    if name not in sys.modules:
        m = _Stub(name)
        m.__stub__ = True
        sys.modules[name] = m

os.environ.setdefault("UGF_AUDIT_PROBE", "1")

res = {"module": MOD, "ok": False, "error": None, "stubbed": []}
try:
    mod = importlib.import_module(MOD)
    res["ok"] = True
except BaseException as exc:
    res["error"] = f"{type(exc).__name__}: {exc}"
    tb = traceback.format_exc().strip().splitlines()
    res["trace"] = tb[-4:]
finally:
    res["stubbed"] = [n for n in STUBS if getattr(sys.modules.get(n), "__stub__", False)]
print("@@JSON@@" + json.dumps(res))
'''


def probe_import(mod: str, stubs: list[str], timeout: int = 20) -> dict:
    cmd = [sys.executable, "-c", PROBE_SRC, json.dumps(stubs), mod, str(ROOT)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"module": mod, "ok": False, "error": f"TimeoutError: 导入超过 {timeout}s（疑似顶层阻塞副作用）",
                "stubbed": []}
    for line in out.stdout.splitlines():
        if line.startswith("@@JSON@@"):
            try:
                res = json.loads(line[len("@@JSON@@"):])
                # 区分"代码缺陷"与"stub 无法模拟第三方 API"两种失败
                res["stub_limited"] = bool(res.get("error")) and "_Stub" in (res.get("error") or "")
                return res
            except json.JSONDecodeError:
                break
    err = (out.stderr or "").strip().splitlines()
    return {"module": mod, "ok": False, "error": "; ".join(err[-3:]) or "未知导入失败",
            "stubbed": [], "stub_limited": False}


# --------------------------------------------------------------------------- #
# 4. 交叉核对
# --------------------------------------------------------------------------- #
def resolve_local(target_mod: str, registry: dict[str, ModuleInfo]) -> ModuleInfo | None:
    """把 `from tools.add_game import x` 之类解析到 registry 键。"""
    if target_mod in registry:
        return registry[target_mod]
    dotted = target_mod.replace(".", "/")
    for key, info in registry.items():
        if key == dotted or key.endswith("/" + dotted):
            return info
    return None


def lookup_symbol(info: ModuleInfo, sym: str) -> bool:
    if sym in info.defs or sym in info.class_methods:
        return True
    if "." in sym:
        return sym in info.class_methods
    return False


def cross_check(registry: dict[str, ModuleInfo]) -> dict:
    missing_symbols: list[dict] = []
    bad_kwargs: list[dict] = []
    missing_attrs: list[dict] = []

    for name, info in registry.items():
        for imp in info.imports:
            if imp["kind"].startswith("from") and imp["level"] == 0:
                tgt = resolve_local(imp["module"], registry)
                if tgt is None or tgt.name == name:
                    continue
                for sym in imp["names"]:
                    if sym == "*":
                        continue
                    if not lookup_symbol(tgt, sym):
                        missing_symbols.append({
                            "from": name, "imports_from": tgt.name, "symbol": sym,
                            "line": imp["line"],
                            "available": sorted(list(tgt.defs)[:40]),
                        })

    # 本地符号调用的关键字参数核对（仅报"明显错误"：未知 kwargs）
    for name, info in registry.items():
        local_names = {n.split(".")[0]: n for n in registry}
        for call in info.calls:
            tgt_mod = None
            if call["qual"] and call["qual"] in local_names:
                tgt_mod = local_names[call["qual"]]
            elif call["target"] in info.defs or call["target"] in info.class_methods:
                tgt_mod = name
            if not tgt_mod or tgt_mod not in registry:
                continue
            tinfo = registry[tgt_mod]
            sig = tinfo.defs.get(call["target"]) or tinfo.class_methods.get(call["target"])
            if not sig or not sig["args"]:
                continue
            params = sig["args"]
            accepts_kwargs = any(p.startswith("**") for p in params)
            if accepts_kwargs:
                continue
            unknown = [k for k in call["kwargs"] if k not in params]
            if unknown:
                bad_kwargs.append({
                    "from": name, "line": call["line"], "call": call["target"],
                    "unknown_kwargs": unknown, "params": params,
                })

    # 模块别名上的属性引用核对：cfg.foo() 中 foo 是否为 config 的顶层符号
    mod_keys = set(registry)
    for name, info in registry.items():
        for ref in info.attr_refs:
            target = info.aliases.get(ref["base"])
            if not target:
                continue
            tgt = resolve_local(target, registry)
            if tgt is None or tgt.name == name:
                continue
            if ref["attr"].startswith("__"):
                continue
            if not lookup_symbol(tgt, ref["attr"]):
                missing_attrs.append({
                    "from": name, "line": ref["line"], "module_alias": ref["base"],
                    "resolved_to": tgt.name, "attr": ref["attr"],
                    "available": sorted(list(tgt.defs)[:40]),
                })
    return {"missing_symbols": missing_symbols, "bad_kwargs": bad_kwargs,
            "missing_attrs": missing_attrs}


def check_requirements(registry: dict[str, ModuleInfo]) -> dict:
    """比对 requirements*.txt 声明 与 代码实际 import 的第三方包。"""
    def parse_req(path: Path) -> dict[str, str]:
        out = {}
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#")[0].strip()
            if not line:
                continue
            name = line
            for sep in ("<=", ">=", "==", "~=", "!=", "<", ">", "[", ";"):
                if sep in name:
                    name = name.split(sep)[0]
            out[name.strip().lower().replace("_", "-")] = line
        return out

    req = parse_req(ROOT / "requirements.txt")
    dev = parse_req(ROOT / "requirements-dev.txt")
    declared = {**req, **dev}

    used: dict[str, set] = {}
    for name, info in registry.items():
        for imp in info.imports:
            root = imp["module"].split(".")[0]
            if not root or imp["level"] > 0:
                continue
            if resolve_local(imp["module"], registry):
                continue
            if classify_third_party(root) == "stdlib":
                continue
            used.setdefault(root.lower().replace("_", "-"), set()).add(name)

    alias = {"pillow": "pil", "opencv-python": "cv2", "opencv-python-headless": "cv2",
             "pyyaml": "yaml", "python-dotenv": "dotenv"}

    def key_of(pkg: str) -> str:
        k = pkg.lower().replace("_", "-")
        return alias.get(k, k)

    declared_keys = {key_of(k): k for k in declared}
    dev_set = set(dev)
    undeclared, unused = [], []
    for u, mods in used.items():
        if u not in declared_keys:
            undeclared.append({"package": u, "used_by": sorted(mods)})
    for d in req:  # 仅运行依赖参与"声明未使用"判定，dev 工具链不 import 属正常
        if key_of(d) not in used:
            unused.append({"package": d, "spec": req[d]})
    data_dev = {"declared_dev": dev_set}

    installed = {}
    for d in declared:
        try:
            from importlib import metadata
            installed[d] = metadata.version(d)
        except Exception:
            installed[d] = None
    return {"declared": req, "declared_dev": dev, "used": {k: sorted(v) for k, v in used.items()},
            "undeclared": sorted(undeclared, key=lambda x: x["package"]),
            "unused": sorted(unused, key=lambda x: x["package"]),
            "installed": installed}


def check_namespace_shadow() -> list[dict]:
    """本地顶层目录若与已安装发行包同名且缺 __init__.py，会被第三方包遮蔽。"""
    import importlib.util
    out = []
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir() or d.name in SKIP_DIRS or d.name.startswith("."):
            continue
        if not any(d.glob("*.py")):
            continue
        if (d / "__init__.py").exists():
            continue
        try:
            spec = importlib.util.find_spec(d.name)
        except (ImportError, ValueError):
            spec = None
        if spec and spec.origin and "site-packages" in str(spec.origin):
            out.append({"dir": d.name, "shadowed_by": str(spec.origin),
                        "py_files": [p.name for p in sorted(d.glob("*.py"))]})
    return out


# --------------------------------------------------------------------------- #
# 5. 主流程
# --------------------------------------------------------------------------- #
def classify_third_party(mod: str) -> str:
    root = mod.split(".")[0]
    if root in STDLIB:
        return "stdlib"
    if root in OPTIONAL_STUBS:
        return "optional"
    return "third-party"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--no-probe", action="store_true", help="跳过导入探针（更快，仅静态分析）")
    args = ap.parse_args()

    started = time.time()
    files = sorted(iter_py_files(ROOT))
    registry: dict[str, ModuleInfo] = {}
    for f in files:
        registry[mod_name_of(f)] = parse_module(f, mod_name_of(f))

    # 依赖图
    dep_graph: dict[str, dict] = {}
    third_party: dict[str, set] = {}
    for name, info in registry.items():
        local_deps, tp_deps, stubbed = set(), set(), set()
        for imp in info.imports:
            root = imp["module"].split(".")[0]
            if imp["level"] > 0 or (imp["module"] and resolve_local(imp["module"], registry)):
                if imp["module"]:
                    local_deps.add(imp["module"])
                continue
            kind = classify_third_party(root)
            if kind == "stdlib":
                continue
            tp_deps.add(root)
            if kind == "optional":
                stubbed.add(root)
                third_party.setdefault(root, set()).add(name)
        dep_graph[name] = {"local": sorted(local_deps), "third_party": sorted(tp_deps),
                           "optional_stubbed": sorted(stubbed)}

    # 导入探针
    probes: dict[str, dict] = {}
    if not args.no_probe:
        stub_list = sorted(OPTIONAL_STUBS)
        targets = [n for n in registry if not n.startswith("tools.static_audit")]
        with mp.get_context("fork").Pool(min(6, os.cpu_count() or 4)) as pool:
            results = pool.starmap(probe_import, [(t, stub_list) for t in targets])
        for r in results:
            probes[r["module"]] = r

    cross = cross_check(registry)
    reqs = check_requirements(registry)
    shadow = check_namespace_shadow()

    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0],
        "root": str(ROOT),
        "modules": {
            n: {
                "path": str(registry[n].path.relative_to(ROOT)),
                "loc": registry[n].loc,
                "syntax_error": registry[n].syntax_error,
                "imports": registry[n].imports,
                "defs": {k: {"kind": v["kind"], "args": v["args"], "line": v["line"]}
                         for k, v in registry[n].defs.items()},
                "methods": list(registry[n].class_methods),
                "placeholders": registry[n].placeholders,
                "markers": registry[n].markers,
            } for n in registry
        },
        "dep_graph": dep_graph,
        "third_party_usage": {k: sorted(v) for k, v in sorted(third_party.items())},
        "probes": probes,
        "cross_check": cross,
        "requirements": reqs,
        "namespace_shadow": shadow,
        "optional_stubs": OPTIONAL_STUBS,
    }

    out_dir = ROOT / "devplan"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "audit_data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[audit] 解析 {len(registry)} 个模块，耗时 {time.time()-started:.1f}s")
    print(f"[audit] 跨模块缺失符号 {len(cross['missing_symbols'])} 处；"
          f"缺失属性 {len(cross['missing_attrs'])} 处；可疑 kwargs {len(cross['bad_kwargs'])} 处")
    print(f"[audit] 未声明依赖 {len(reqs['undeclared'])} 个；声明但未使用 {len(reqs['unused'])} 个；"
          f"命名空间遮蔽 {len(shadow)} 处")
    if probes:
        ok = sum(1 for p in probes.values() if p["ok"])
        print(f"[audit] 导入探针：{ok}/{len(probes)} 成功")
        for n, p in probes.items():
            if not p["ok"]:
                print(f"    ✗ {n}: {p['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
