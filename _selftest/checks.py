# -*- coding: utf-8 -*-
"""压力测试器自检脚本（不属于交付物，验证完可以整个删掉 _selftest 目录）

用法：
    python _selftest/checks.py
"""

import ctypes
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MAIN = ROOT / "main.py"
WORK = HERE / "work"
TARGETS = WORK / "targets"
OUT = WORK / "out"
PY = sys.executable

INPUT_HDR = "---------- 输入数据（完整喂给被测试程序的 stdin）----------"
OUTPUT_HDR = "---------- 被测试程序的输出 / 报错信息 ----------"

_results = []


def check(name, ok, detail="") -> bool:
    _results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("   -> " + detail) if detail else ""), flush=True)
    return bool(ok)


def skip(name, detail="") -> None:
    print("SKIP  " + name + (("   -> " + detail) if detail else ""), flush=True)


def run_main(args, timeout=180):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["SELFTEST_PIDFILE"] = str(TARGETS / "pids.txt")
    started = time.perf_counter()
    proc = subprocess.run(
        [PY, str(MAIN), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(ROOT), timeout=timeout,
    )
    return proc, time.perf_counter() - started


def last_line(text):
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def stat_line_ok(text):
    return re.fullmatch(r"通过 \d+ 组 / 崩 \d+ 组 / 超时 \d+ 组", last_line(text)) is not None


def extract_input(text):
    return text.split(INPUT_HDR, 1)[1].split(OUTPUT_HDR, 1)[0].strip()


def group_of(text):
    m = re.search(r"第 (\d+) 组数据", text)
    return int(m.group(1)) if m else -1


def pid_alive(pid):
    """用 OpenProcess + GetExitCodeProcess 判断进程是否还活着。

    比 tasklist 可靠：受限环境下 tasklist 自己就可能被拒绝而输出为空，
    那样"查不到"会被误当成"已经死了"。
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True   # 打不开退出码，保守认为还活着
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def taskkill_works_here():
    """先量一下：这个环境里 taskkill 能不能杀掉自己起的进程。

    某些受限令牌（比如沙箱）会让 taskkill 报"拒绝访问"，
    这属于环境限制，不代表压力测试器的代码有问题。
    """
    victim = subprocess.Popen([PY, "-c", "import time; time.sleep(30)"])
    try:
        time.sleep(0.3)
        r = subprocess.run(["taskkill", "/F", "/PID", str(victim.pid)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        alright = r.returncode == 0 and pid_alive(victim.pid) is False
        return alright, (r.stdout + r.stderr).strip()
    finally:
        try:
            victim.kill()
            victim.wait(timeout=5)
        except Exception:
            pass


def kill_pid(pid):
    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


# --------------------------------------------------------------------------- #
# 准备被测目标与生成规则
# --------------------------------------------------------------------------- #
def prepare():
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    TARGETS.mkdir(parents=True)
    OUT.mkdir(parents=True)

    files = {
        # 1. 语法错误：必定崩溃，且报错信息里带 SyntaxError
        "syntax_error.py": "def broken(:\n    pass\n",
        # 2. 死循环：必定超时
        "hang.py": "import time\nprint('start', flush=True)\ntime.sleep(120)\n",
        # 3. 自己再起一个子进程一起挂住：验证 taskkill /T 连子进程一起收掉
        "child_hang.py": (
            "import os, subprocess, sys, time\n"
            "from pathlib import Path\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            "Path(os.environ['SELFTEST_PIDFILE']).write_text(f'{os.getpid()} {child.pid}', encoding='utf-8')\n"
            "print('hanging', flush=True)\n"
            "time.sleep(120)\n"
        ),
        # 4. 交互式：连读两行，和为 0 就崩（用来验证 stdin 是真的喂进去了）
        "interactive.py": (
            "a = int(input())\n"
            "b = int(input())\n"
            "print(a + b)\n"
            "assert a + b != 0, 'sum is zero'\n"
        ),
        # 5. 崩溃但没有任何输出
        "silent_crash.py": "import sys\nsys.exit(3)\n",
        # 6. 大量输出：验证管道不会死锁
        "chatty.py": "for i in range(200000):\n    print('line', i)\n",
        # 7. 永远正常
        "always_ok.py": "import sys\nsys.stdin.read()\nprint('ok')\n",
    }
    for name, code in files.items():
        (TARGETS / name).write_text(code, encoding="utf-8")

    gens = {
        "gen_ok.py": (
            "import random\n"
            "def gen():\n"
            "    return '%d\\n' % random.randint(1, 1000)\n"
        ),
        # 返回的不是字符串：应当被转成字符串，不报错
        "gen_int.py": "import random\ndef gen():\n    return random.randint(1, 100)\n",
        # 没有 gen() 函数
        "gen_missing.py": "import random\n\ndef make():\n    return '1\\n'\n",
        # 每次返回两个整数，正好喂给 interactive.py
        "gen_pair.py": (
            "import random\n"
            "def gen():\n"
            "    a = random.randint(0, 3)\n"
            "    b = random.randint(-2, 2)\n"
            "    return '%d\\n%d\\n' % (a, b)\n"
        ),
        # 导入时直接炸掉
        "gen_boom.py": "raise RuntimeError('gen.py 自己就崩了')\n",
        "gen_crashy.py": (
            "import random\n"
            "def gen():\n"
            "    if random.random() < 0.5:\n"
            "        raise ValueError('生成失败')\n"
            "    return '1\\n'\n"
        ),
    }
    for name, code in gens.items():
        (TARGETS / name).write_text(code, encoding="utf-8")


def gen_path(name):
    return str(TARGETS / name)


def target(name):
    return str(TARGETS / name)


# --------------------------------------------------------------------------- #
# 各项检查
# --------------------------------------------------------------------------- #
def main():
    prepare()
    out1 = OUT / "r1"
    out2 = OUT / "r2"

    # ---- 1. 崩溃 + fail_*.txt 内容 --------------------------------------- #
    proc, _ = run_main([target("syntax_error.py"), "--count", "7", "--seed", "42", "--outdir", str(out1)])
    check("崩溃：返回码为 1", proc.returncode == 1, f"exit={proc.returncode}")
    check("崩溃：统计行格式正确", stat_line_ok(proc.stdout), repr(last_line(proc.stdout)))
    check("崩溃：统计为 崩 7 组", "崩 7 组" in proc.stdout and "通过 0 组" in proc.stdout)
    fail_files = sorted(out1.glob("fail_*.txt"))
    check("崩溃：只写前 5 个失败文件", [f.name for f in fail_files] == [f"fail_{i}.txt" for i in range(1, 6)],
          str([f.name for f in fail_files]))
    text1 = (out1 / "fail_1.txt").read_text(encoding="utf-8")
    check("失败文件：含输入数据", INPUT_HDR in text1 and extract_input(text1) != "")
    check("失败文件：含报错信息", "SyntaxError" in text1 and OUTPUT_HDR in text1)
    check("失败文件：记录组号与种子", group_of(text1) == 1 and "随机种子  : 42" in text1,
          f"group={group_of(text1)}")

    # ---- 2. 超时 ---------------------------------------------------------- #
    proc, elapsed = run_main([target("hang.py"), "--count", "3", "--seed", "1", "--timeout", "1.0"])
    check("超时：返回码为 1", proc.returncode == 1, f"exit={proc.returncode}")
    check("超时：统计为 超时 3 组", "超时 3 组" in proc.stdout, repr(last_line(proc.stdout)))
    check("超时：确实在超时点被杀掉（3 组约 3 秒）", 2.5 <= elapsed <= 12, f"{elapsed:.2f}s")
    check("超时：不写失败文件", not list(OUT.glob("fail_*.txt")))

    # ---- 3. 超时后连子进程一起收掉 --------------------------------------- #
    tree_ok, tree_detail = taskkill_works_here()
    pidfile = TARGETS / "pids.txt"
    if pidfile.exists():
        pidfile.unlink()
    proc, elapsed = run_main([target("child_hang.py"), "--count", "1", "--seed", "1", "--timeout", "1.0"],
                             timeout=180)
    pids = []
    if pidfile.exists():
        pids = [int(x) for x in pidfile.read_text(encoding="utf-8").split()]
    check("超时杀进程树：目标进程留下了 pid 记录", len(pids) == 2, str(pids))
    check("超时杀进程树：孙子进程攥着管道也不会卡住（1 秒超时，不该等十几秒）",
          elapsed <= 6, f"{elapsed:.2f}s")
    if len(pids) == 2:
        time.sleep(0.5)
        still = [p for p in pids if pid_alive(p)]
        if tree_ok:
            check("超时杀进程树：目标和它的子进程都已被杀死", not still, f"still alive: {still}")
        else:
            skip("超时杀进程树：目标和它的子进程都已被杀死",
                 f"本环境禁止 taskkill（{tree_detail}），普通控制台下才能验证整棵树")
        for p in still:
            kill_pid(p)

    # ---- 4. stdin 真的喂进去了 -------------------------------------------- #
    proc, _ = run_main([target("interactive.py"), "--gen", gen_path("gen_pair.py"),
                        "--count", "40", "--seed", "9", "--outdir", str(OUT / "r3")])
    check("交互程序：0+0 时确实崩了（说明 stdin 内容正确）",
          "崩 " in proc.stdout and "崩 0 组" not in proc.stdout, repr(last_line(proc.stdout)))
    f = OUT / "r3" / "fail_1.txt"
    check("交互程序：失败文件里能看到断言报错", f.exists() and "AssertionError" in f.read_text(encoding="utf-8"))

    # ---- 5. 崩溃但无输出 -------------------------------------------------- #
    proc, _ = run_main([target("silent_crash.py"), "--count", "2", "--seed", "3", "--outdir", str(OUT / "r4")])
    t = (OUT / "r4" / "fail_1.txt").read_text(encoding="utf-8")
    check("无输出的崩溃：写入 (没有任何输出)", "(没有任何输出)" in t and "返回码    : 3" in t)

    # ---- 6. 大量输出不死锁 ------------------------------------------------ #
    proc, elapsed = run_main([target("chatty.py"), "--count", "2", "--seed", "4", "--quiet"])
    check("大量输出：正常跑完且全部通过", proc.returncode == 0 and "通过 2 组" in proc.stdout,
          f"exit={proc.returncode} {last_line(proc.stdout)} {elapsed:.2f}s")

    # ---- 7. 全部通过时返回 0 ---------------------------------------------- #
    proc, _ = run_main([target("always_ok.py"), "--count", "15", "--seed", "5", "--quiet"])
    check("全部通过：返回码 0", proc.returncode == 0, f"exit={proc.returncode}")
    check("全部通过：统计行为 通过 15 组 / 崩 0 组 / 超时 0 组",
          last_line(proc.stdout) == "通过 15 组 / 崩 0 组 / 超时 0 组", repr(last_line(proc.stdout)))
    check("--quiet：没有逐组进度行", "[   1/15]" not in proc.stdout)

    # ---- 8. gen() 返回非字符串 -------------------------------------------- #
    proc, _ = run_main([target("always_ok.py"), "--gen", gen_path("gen_int.py"),
                        "--count", "5", "--seed", "6", "--quiet"])
    check("gen() 返回 int：自动转成字符串，不报错", proc.returncode == 0, f"exit={proc.returncode}")

    # ---- 9. 种子复现 ------------------------------------------------------ #
    out3 = OUT / "r6"
    out4 = OUT / "r7"
    proc_a, _ = run_main([str(ROOT / "example_target.py"),
                          "--count", "200", "--seed", "123", "--quiet", "--outdir", str(out3)])
    proc_b, _ = run_main([str(ROOT / "example_target.py"),
                          "--count", "200", "--seed", "123", "--quiet", "--outdir", str(out4)])
    check("复现：两次同种子统计完全一致",
          last_line(proc_a.stdout) == last_line(proc_b.stdout), f"{last_line(proc_a.stdout)} | {last_line(proc_b.stdout)}")
    groups_a = [group_of((out3 / f"fail_{i}.txt").read_text(encoding="utf-8")) for i in range(1, 6)]
    groups_b = [group_of((out4 / f"fail_{i}.txt").read_text(encoding="utf-8")) for i in range(1, 6)]
    check("复现：崩溃组号完全一致", groups_a == groups_b, f"{groups_a} vs {groups_b}")
    inputs_a = [extract_input((out3 / f"fail_{i}.txt").read_text(encoding="utf-8")) for i in range(1, 6)]
    inputs_b = [extract_input((out4 / f"fail_{i}.txt").read_text(encoding="utf-8")) for i in range(1, 6)]
    check("复现：前 5 组崩溃输入数据逐字节一致", inputs_a == inputs_b)

    # ---- 10. 换种子应当产生不同数据 --------------------------------------- #
    proc_c, _ = run_main([str(ROOT / "example_target.py"), "--count", "200", "--seed", "999",
                          "--quiet", "--outdir", str(OUT / "r5")])
    check("换种子：统计与 seed=123 不同", last_line(proc_c.stdout) != last_line(proc_a.stdout),
          f"{last_line(proc_a.stdout)} | {last_line(proc_c.stdout)}")

    # ---- 11. 不给种子也能跑，并打印可复现的种子 --------------------------- #
    proc, _ = run_main([target("always_ok.py"), "--count", "3", "--quiet"])
    m = re.search(r"随机种子    : (\d+)", proc.stdout)
    check("不带 --seed：自动生成种子并打印出来", bool(m), repr(m.group(0) if m else proc.stdout))

    # ---- 12. 错误路径 ----------------------------------------------------- #
    proc, _ = run_main(["not_exist.py"])
    check("目标文件不存在：退出码 2 且提示清楚",
          proc.returncode == 2 and "找不到被测试程序" in proc.stderr, f"exit={proc.returncode}")

    proc, _ = run_main([target("always_ok.py"), "--gen", gen_path("gen_missing.py")])
    check("gen.py 里没有 gen()：退出码 2 且提示清楚",
          proc.returncode == 2 and "没有找到可调用的 gen()" in proc.stderr, repr(proc.stderr[-90:]))

    proc, _ = run_main([target("always_ok.py"), "--gen", gen_path("gen_boom.py")])
    check("gen.py 导入即崩：退出码 2 且提示清楚",
          proc.returncode == 2 and "执行 gen_boom.py 时出错" in proc.stderr, repr(proc.stderr[-90:]))

    proc, _ = run_main([target("always_ok.py"), "--gen", gen_path("gen_crashy.py"), "--count", "10", "--quiet"])
    check("gen() 中途抛异常：退出码 2 且说明是第几组",
          proc.returncode == 2 and re.search(r"生成第 \d+ 组数据时出错", proc.stderr) is not None,
          repr(proc.stderr[-90:]))

    proc, _ = run_main([str(ROOT / "example_target.py"), "--count", "0"])
    check("--count 0：退出码 2", proc.returncode == 2, f"exit={proc.returncode}")

    proc, _ = run_main([str(ROOT / "example_target.py"), "--count", "1", "--gen", str(OUT / "nope.py")])
    check("--gen 指向的文件不存在：退出码 2", proc.returncode == 2 and "找不到数据生成规则文件" in proc.stderr)

    # ---- 13. 结尾统计行就是最后一行 --------------------------------------- #
    check("结尾：统计行是屏幕最后一行", stat_line_ok(proc_a.stdout))

    failed = [name for name, ok in _results if not ok]
    print("\n" + "=" * 60)
    print(f"自检结果：{len(_results) - len(failed)} 项通过 / {len(failed)} 项失败")
    if failed:
        for name in failed:
            print("  FAILED: " + name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
