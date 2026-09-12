#!/usr/bin/env python3
"""
FlorrVLM-Agent 资源调度器 resource_guard.py
=============================================
v2.0 —— J1900 低配 7×24 稳定运行的资源守护。

只做三件事，全部纯标准库（不装 psutil）：
  1. 采样：当前进程 + 子进程的内存(RSS) / CPU 占用，写 run_logs/resource.log
  2. 软超限降级：内存超 mem_limit_mb 时，依次
       清理临时帧目录 → 压缩陈旧日志 → 归档知识库（保护小硬盘）
  3. 硬超限告警：内存超 mem_hard_mb 时追加 STRONG 告警（进程是否重启交给 watchdog）

用法:
  python resource_guard.py --once     # 检查一次（供测试/脚本调用）
  python resource_guard.py            # 守护循环（start_all.sh 后台拉起）
"""
import argparse
import os
import time

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"))
RES_LOGFILE = os.path.join(LOG_DIR, "resource.log")
FRAMES_DIR = os.path.join(BASE_DIR, config.get("paths.frames", "video_frames"))


# ---------------------------------------------------------------------------
# 采样（纯 /proc，Linux only；其他系统返回 None 跳过）
# ---------------------------------------------------------------------------
def _read_int(path: str) -> int:
    try:
        with open(path, "r") as f:
            return int(f.read().split()[0])
    except (OSError, IndexError, ValueError):
        return 0


def _rss_kb_of(pid: int) -> int:
    """读 /proc/<pid>/status 的 VmRSS(KB)。"""
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, IndexError, ValueError):
        pass
    return 0


def _total_rss_kb() -> int:
    """当前进程 + 全部子进程的 RSS 总和(KB)。"""
    me = os.getpid()
    total = _rss_kb_of(me)
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/stat") as f:
                    parts = f.read().split()
                if parts[3] == str(me):  # 父进程 = 本进程
                    total += _rss_kb_of(int(entry))
            except (OSError, IndexError, ValueError):
                continue
    except OSError:
        pass
    return total


class _CpuSampler:
    """进程级 CPU%：读 /proc/self/stat 的 utime+stime 差值与真实时间比。

    只统计本进程(含累加时把子进程算进 sample)，共享主机/多租户下也准确。
    首次调用只设基线返回 0。
    """

    def __init__(self):
        self._last = 0.0
        self._last_t = 0.0

    def _cpu_secs(self, pid: int) -> float:
        """进程 CPU 秒(utime+stime，/proc/stat 单位是时钟节拍，转秒)。"""
        try:
            with open(f"/proc/{pid}/stat") as f:
                parts = f.read().split()
            # 字段索引: utime=13(0-based), stime=14
            return (int(parts[13]) + int(parts[14])) / 100.0
        except (OSError, IndexError, ValueError):
            return 0.0

    def cpu_pct(self, include_children: bool = True) -> float:
        me = os.getpid()
        now = self._cpu_secs(me)
        if include_children:
            try:
                for entry in os.listdir("/proc"):
                    if not entry.isdigit():
                        continue
                    try:
                        with open(f"/proc/{entry}/stat") as f:
                            parts = f.read().split()
                        if parts[3] == str(me):
                            now += self._cpu_secs(int(entry))
                    except (OSError, IndexError, ValueError):
                        continue
            except OSError:
                pass
        now_t = time.monotonic()
        if self._last <= 0:
            self._last, self._last_t = now, now_t
            return 0.0
        dt = now_t - self._last_t
        # 时钟分辨率有限，间隔太短(<1s)不采信
        pct = 0.0
        if dt >= 1.0:
            pct = (now - self._last) / dt * 100.0
        self._last, self._last_t = now, now_t
        return round(min(pct, 100.0), 1)


def sample() -> dict:
    """返回 {rss_mb, cpu_pct, pid, ts}。非 Linux 环境 rss_mb 可能为 0。"""
    rss_kb = _total_rss_kb()
    return {
        "pid": os.getpid(),
        "rss_mb": round(rss_kb / 1024, 1),
        "cpu_pct": _CPU_SAMPLER.cpu_pct(),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


_CPU_SAMPLER = _CpuSampler()


# ---------------------------------------------------------------------------
# 降级动作（软超限时按顺序执行）
# ---------------------------------------------------------------------------
def _clean_frames() -> str:
    """清理视频抽帧临时目录。"""
    if not os.path.isdir(FRAMES_DIR):
        return ""
    import shutil
    try:
        shutil.rmtree(FRAMES_DIR)
        return "已清理临时帧目录 video_frames/"
    except OSError as e:
        return f"清理临时帧失败: {e}"


def _clean_old_logs():
    """删除超过 retention_days 的旧日志；压缩超过 max_size_mb 的大日志。"""
    import gzip
    import shutil
    days = config.get("logs.retention_days", 7)
    max_kb = config.get("logs.max_size_mb", 20) * 1024
    cutoff = time.time() - days * 86400
    done = []
    if not os.path.isdir(LOG_DIR):
        return []
    for fn in os.listdir(LOG_DIR):
        fp = os.path.join(LOG_DIR, fn)
        if not os.path.isfile(fp):
            continue
        try:
            if os.path.getmtime(fp) < cutoff and fn != "resource.log":
                os.remove(fp)
                done.append(f"删旧日志 {fn}")
            elif os.path.getsize(fp) > max_kb * 1024 and not fn.endswith(".gz"):
                with open(fp, "rb") as src, gzip.open(fp + ".gz", "wb") as dst:
                    shutil.copyfileobj(src, dst)
                os.remove(fp)
                done.append(f"压缩日志 {fn}")
        except OSError:
            continue
    return done


def _archive_kb():
    """知识库超上限时归档最早的笔记（复用 kb_maintainer）。"""
    try:
        import kb_maintainer
        kb, arch = kb_maintainer._paths()
        moved = kb_maintainer.archive_oldest(
            kb, arch, config.get("agent.kb_max_mb", 50.0))
        if moved:
            return f"已归档知识库最早笔记 {moved} 份"
    except Exception:
        pass
    return ""


def _run_degrade() -> list:
    """软超限降级：清帧 → 清日志 → 归档知识库。返回执行的动作列表。"""
    acts = []
    acts.append(_clean_frames() or "")
    acts += _clean_old_logs()
    acts.append(_archive_kb())
    return [a for a in acts if a]


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def check_once(log: bool = True) -> str:
    """检查一次并返回结果文本。log=True 同时写入 run_logs/resource.log。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    s = sample()
    mem_mb = s["rss_mb"]
    cpu = s["cpu_pct"]
    mem_soft = config.get("resource.mem_limit_mb", 500)
    mem_hard = config.get("resource.mem_hard_mb", 1000)
    cpu_lim = config.get("resource.cpu_limit_pct", 80)

    line = (f"[资源] 内存 {mem_mb:.1f}MB(软限 {mem_soft} / 硬限 {mem_hard}) "
            f"CPU {cpu:.1f}% (限 {cpu_lim}%)")
    if mem_mb > mem_hard:
        line += "\n! STRONG 硬超限! 内存超过硬上限，建议人工检查或交给 watchdog 重启"
    elif mem_mb > mem_soft:
        acts = _run_degrade()
        line += "\n| 软超限，降级: " + ("；".join(acts) if acts else "无可用动作")
    elif cpu > cpu_lim:
        line += "\n| CPU 超限告警(不降级，仅记录，留意是否卡循环)"

    if log:
        try:
            with open(RES_LOGFILE, "a", encoding="utf-8") as f:
                f.write(f"{s['ts']} pid={s['pid']} " + line.replace("\n", " | ") + "\n")
        except OSError:
            pass
    return line


def watch_loop(interval: int = None):
    """守护循环：每 interval 秒检查一次。"""
    interval = interval or config.get("resource.check_interval", 30)
    print(f"[resource_guard] 守护启动，每 {interval}s 检查一次 (日志 {RES_LOGFILE})")
    while True:
        try:
            print(check_once())
        except Exception as e:
            print(f"[resource_guard] 检查异常: {e}")
        time.sleep(max(5, interval))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="资源调度器")
    ap.add_argument("--once", action="store_true", help="只检查一次（测试/手动）")
    ap.add_argument("--interval", type=int, default=None, help="守护检查间隔秒")
    args = ap.parse_args()
    if args.once:
        print(check_once())
    else:
        watch_loop(args.interval)