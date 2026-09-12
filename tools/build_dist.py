#!/usr/bin/env python3
"""
FlorrVLM-Agent 系统安装包打包  tools/build_dist.py  (v1.9)
=========================================================
把一个仓库做成可直接分发的安装包，覆盖四类平台：

  1) Linux  .deb   —— 本机就能打（依赖 dpkg-deb），装完有 florrvlm-agent 命令
  2) Linux 免安装 —— tar.gz 便携包（解压即用，不装系统）
  3) Windows EXE/便携—— 在 Windows 上跑 build_windows.bat 生成 exe + zip
  4) Android APK    —— 在 Windows/Mac/Linux 上装 buildozer 后打（见 README）

用法：
  python tools/build_dist.py deb           # 打 Linux .deb（唯一本机可直接验证的）
  python tools/build_dist.py portable      # 打 Linux 免安装 tar.gz
  python tools/build_dist.py all           # deb + portable
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist")
PKG = "florrvlm-agent"
VERSION = os.getenv("PKG_VERSION", "1.9.0")

# 打包所需文件：整个仓库里这些都要进包（除了运行时/缓存/大文件）
SHIP_DIRS = ["game_profiles", "skills", "tools"]
SHIP_FILES = [
    "agent_cli.py", "agent_main.py", "admin_panel.py", "auto_tuner.py",
    "boot_check.py", "cli_ui.py", "combat_judge.py", "config.py", "config.yaml",
    "game_profile_check.py", "kb_maintainer.py", "mcp_connector.py",
    "mcp_connectors.yaml", "mcp_server.py", "perception_server.py", "predictor.py",
    "report_notifier.py", "session.py", "skill_manager.py", "video_learner.py",
    "video_sources.py", "requirements.txt", "ROADMAP.md", "README.md",
    ".env.example",
]


def ensure_out():
    os.makedirs(OUT, exist_ok=True)


def stage_tree(dest: str):
    """把仓库源码铺到一个临时目录，供后续打包。"""
    os.makedirs(dest, exist_ok=True)
    for d in SHIP_DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, d), dirs_exist_ok=True)
    for f in SHIP_FILES:
        s = os.path.join(ROOT, f)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dest, f))
    # 清掉运行产物（快照/历史/临时回调都不该进包）
    for skip in ("__pycache__", "run_logs", "video_frames", "knowledge_md",
                 "session_history.json", "agent_state.json", "tuned_overrides.yaml"):
        p = os.path.join(dest, skip)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.isfile(p):
            os.remove(p)


# ---------------------------------------------------------------------------
# Linux .deb
# ---------------------------------------------------------------------------
def build_deb() -> str:
    if not shutil.which("dpkg-deb"):
        raise RuntimeError("缺少 dpkg-deb（Debian/Ubuntu 自带，先 apt install dpkg）")
    tmp = tempfile.mkdtemp(prefix="florrvlm_deb_")
    try:
        rootpkg = os.path.join(tmp, "pkg")
        lib = os.path.join(rootpkg, "usr", "lib", PKG)
        bin = os.path.join(rootpkg, "usr", "bin")
        doc = os.path.join(rootpkg, "usr", "share", "doc", PKG)
        os.makedirs(bin, exist_ok=True)
        os.makedirs(doc, exist_ok=True)
        stage_tree(lib)

        # 命令行入口
        launcher = os.path.join(lib, PKG)  # 装在 usr/bin 的脚本
        with open(launcher, "w", encoding="utf-8") as f:
            f.write(
                "#!/usr/bin/env python3\n"
                "import os, sys\n"
                f"sys.path.insert(0, '{lib}')\n"
                f"os.environ['AGENT_ROOT'] = '{lib}'\n"
                "from agent_cli import main\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        os.chmod(launcher, 0o755)
        os.symlink(launcher, os.path.join(bin, "florrvlm-agent"))

        # 文档
        with open(os.path.join(doc, "README.txt"), "w", encoding="utf-8") as f:
            f.write("FlorrVLM-Agent v%s\n查看项目 README.md 了解用法。\n" % VERSION)

        # Debian control / 维护脚本
        debin = os.path.join(rootpkg, "DEBIAN")
        os.makedirs(debin, exist_ok=True)
        with open(os.path.join(debin, "control"), "w", encoding="utf-8") as f:
            f.write(
                "Package: %s\n"
                "Version: %s\n"
                "Section: utils\n"
                "Priority: optional\n"
                "Architecture: amd64\n"
                "Depends: python3, python3-yaml, python3-requests, python3-dotenv\n"
                "Maintainer: FlorrVLM-Agent <noreply@example.com>\n"
                "Description: Universal game operation agent (CLI + MCP + dashboard)\n"
                " A visual game agent. Install then run: florrvlm-agent\n"
                % (PKG, VERSION)
            )
        with open(os.path.join(debin, "conffiles"), "w", encoding="utf-8") as f:
            f.write("/usr/lib/%s/config.yaml\n" % PKG)

        with open(os.path.join(debin, "postinst"), "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nset -e\n")
            f.write("mkdir -p /var/lib/%s\nchmod 700 /var/lib/%s\n" % (PKG, PKG))
        os.chmod(os.path.join(debin, "postinst"), 0o755)

        # md5sums 保证软件包完整性校验
        sums = []
        for rootdir, _, files in os.walk(rootpkg):
            if rootdir.endswith("DEBIAN"):
                continue
            for fn in files:
                fp = os.path.join(rootdir, fn)
                rel = os.path.join(os.path.relpath(rootdir, rootpkg), fn)
                h = subprocess.check_output(["md5sum", fp], text=True).split()[0]
                sums.append(f"{h}  {rel}")
        with open(os.path.join(debin, "md5sums"), "w", encoding="utf-8") as f:
            f.write("\n".join(sums) + "\n")

        out = os.path.join(OUT, f"{PKG}_{VERSION}_amd64.deb")
        subprocess.check_call(["dpkg-deb", "--build", rootpkg, out])
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Linux 免安装便携包 tar.gz
# ---------------------------------------------------------------------------
def build_portable() -> str:
    tmp = tempfile.mkdtemp(prefix="florrvlm_port_")
    try:
        rootdir = os.path.join(tmp, PKG)
        stage_tree(rootdir)
        # 免安装入口：解压后直接 ./florrvlm-agent 启动
        with open(os.path.join(rootdir, "florrvlm-agent"), "w", encoding="utf-8") as f:
            f.write(
                "#!/usr/bin/env python3\n"
                "import os, sys\n"
                "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
                "from agent_cli import main\n"
                "main()\n"
            )
        os.chmod(os.path.join(rootdir, "florrvlm-agent"), 0o755)
        out = os.path.join(OUT, f"{PKG}_{VERSION}_portable.tar.gz")
        subprocess.check_call(
            ["tar", "-C", tmp, "-czf", out, PKG])
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(kinds: list = None):
    want = set(kinds) or {"all"}
    ensure_out()
    results = []
    if want & {"deb", "all"}:
        results.append(("Linux .deb", build_deb()))
    if want & {"portable", "all"}:
        results.append(("Linux 便携版", build_portable()))
    print("\n已产出的安装包：")
    for label, path in results:
        size = os.path.getsize(path) / 1024
        print(f"  {label:12s} {path}  ({size:.0f} KB)")
    print("\nWindows EXE/便携 & Android APK：请在对应系统运行 packaging/build_windows.bat / buildozer")
    print("说明见 packaging/README.md")


if __name__ == "__main__":
    main(sys.argv[1:] or ["all"])