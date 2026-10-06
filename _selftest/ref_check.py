# -*- coding: utf-8 -*-
"""对拍（--ref）自检：验证「参考程序出错绝不算成被测试程序错」这条底线，以及比较规则。

用法：
    python _selftest/ref_check.py
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK = HERE / "ref_work"
PY = sys.executable

STATS_RE = re.compile(r"^通过 (\d+) 组 / 崩 (\d+) 组 / 超时 (\d+) 组(?: / 不一致 (\d+) 组)?$")

_results = []


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name
          + (("   -> " + str(detail)) if detail else ""), flush=True)
    return bool(ok)


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def prepare():
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)

    # 固定数据：永远都是 "3\n1 2 3\n"，方便数结果
    write(WORK / "gen_simple.py", (
        "# -*- coding: utf-8 -*-\n"
        "def gen():\n"
        "    return '3\\n1 2 3\\n'\n"
    ))

    read_and_sum = (
        "import sys\n"
        "tok = sys.stdin.read().split()\n"
        "nums = [int(x) for x in tok[1:1 + int(tok[0])]] if tok else []\n"
        "print('sum =', sum(nums))\n"
    )
    write(WORK / "t_ok.py", read_and_sum)                       # 被测试：正确
    write(WORK / "t_crash.py", "import sys\nsys.stdin.read()\nprint('x')\nraise SystemExit(1)\n")
    write(WORK / "t_hang.py", "import sys, time\nsys.stdin.read()\ntime.sleep(30)\n")

    write(WORK / "r_same.py", read_and_sum)                     # 参考：和被测试一样
    write(WORK / "r_diff.py", (                                 # 参考：答案差 1
        "import sys\n"
        "tok = sys.stdin.read().split()\n"
        "nums = [int(x) for x in tok[1:1 + int(tok[0])]] if tok else []\n"
        "print('sum =', sum(nums) + 1)\n"
    ))
    write(WORK / "r_ws.py", (                                   # 参考：只多空白，应该算通过
        "import sys\n"
        "sys.stdin.read()\n"
        "sys.stdout.write('sum = 6   \\r\\n')\n"
        "sys.stdout.write('\\r\\n')\n"
        "sys.stdout.write('   \\n')\n"
    ))
    write(WORK / "r_crash.py", "import sys\nsys.stdin.read()\nraise SystemExit(3)\n")
    write(WORK / "r_hang.py", "import sys, time\nsys.stdin.read()\ntime.sleep(30)\n")

    marker = WORK / "ref_ran.txt"
    write(WORK / "r_marker.py", (
        "import sys\n"
        "from pathlib import Path\n"
        f"p = Path(r'{marker}')\n"
        "p.write_text((p.read_text(encoding='utf-8') if p.exists() else '') + 'x', encoding='utf-8')\n"
        "tok = sys.stdin.read().split()\n"
        "nums = [int(x) for x in tok[1:1 + int(tok[0])]] if tok else []\n"
        "print('sum =', sum(nums))\n"
    ))

    # 专门用来验证「第一处不同在第几行第几列」
    write(WORK / "t_abc.py", "import sys\nsys.stdin.read()\nprint('abc')\n")
    write(WORK / "r_abd.py", "import sys\nsys.stdin.read()\nprint('abd')\n")
    write(WORK / "t_two.py", "import sys\nsys.stdin.read()\nprint('a')\nprint('b')\n")
    write(WORK / "r_three.py", "import sys\nsys.stdin.read()\nprint('a')\nprint('b')\nprint('c')\n")


def run_main(*args, count=4, seed=7, timeout="2", outdir=None):
    outdir = outdir or (WORK / "out")
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(ROOT / "main.py"), *args,
           "--gen", str(WORK / "gen_simple.py"),
           "--count", str(count), "--seed", str(seed), "--timeout", timeout,
           "--quiet", "--outdir", str(outdir)]
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def stats_of(stdout: str):
    for line in stdout.splitlines():
        m = STATS_RE.match(line.strip())
        if m:
            passed, crashed, timed_out, mismatch = m.groups()
            return (line.strip(), int(passed), int(crashed), int(timed_out),
                    int(mismatch) if mismatch is not None else None)
    return ("", -1, -1, -1, None)


def fresh(name: str) -> Path:
    out = WORK / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    return out


def main():
    prepare()

    # ---- 0. 不给 --ref：统计行必须还是老格式 ----------------------------- #
    out0 = fresh("out0")
    proc = run_main(str(WORK / "t_ok.py"), count=4, outdir=out0)
    stats = stats_of(proc.stdout)[0]
    check("向后兼容：不给 --ref 时统计行还是老格式",
          stats == "通过 4 组 / 崩 0 组 / 超时 0 组" and "不一致" not in proc.stdout, repr(stats))
    check("向后兼容：不给 --ref 时退出码 0", proc.returncode == 0, f"exit={proc.returncode}")

    # ---- 1. 参考程序和被测试程序输出一样 ---------------------------------- #
    out1 = fresh("out1")
    proc = run_main(str(WORK / "t_ok.py"), "--ref", str(WORK / "r_same.py"), count=4, outdir=out1)
    line, passed, crashed, timed_out, mismatch = stats_of(proc.stdout)
    check("对拍：输出一致时全部通过",
          (passed, crashed, timed_out, mismatch) == (4, 0, 0, 0), repr(line))
    check("对拍：全部通过时退出码 0", proc.returncode == 0, f"exit={proc.returncode}")
    check("对拍：没有生成 diff_*.txt", not list(out1.glob("diff_*.txt")))

    # ---- 2. 只差空白 / 空行 / \r：必须算通过 ------------------------------ #
    out2 = fresh("out2")
    proc = run_main(str(WORK / "t_ok.py"), "--ref", str(WORK / "r_ws.py"), count=3, outdir=out2)
    line = stats_of(proc.stdout)[0]
    check("比较规则：行尾空白、末尾空行、行尾 \\r 都被忽略（算通过）",
          line == "通过 3 组 / 崩 0 组 / 超时 0 组 / 不一致 0 组", repr(line))
    check("比较规则：这种情况不该写 diff 文件", not list(out2.glob("diff_*.txt")))

    # ---- 3. 答案不一致：计数、文件、内容 ---------------------------------- #
    out3 = fresh("out3")
    proc = run_main(str(WORK / "t_ok.py"), "--ref", str(WORK / "r_diff.py"), count=8, seed=11, outdir=out3)
    line, passed, crashed, timed_out, mismatch = stats_of(proc.stdout)
    check("不一致：统计行是新格式且计数正确",
          (passed, crashed, timed_out, mismatch) == (0, 0, 0, 8), repr(line))
    check("不一致：退出码是 1", proc.returncode == 1, f"exit={proc.returncode}")
    diffs = sorted(p.name for p in out3.glob("diff_*.txt"))
    check("不一致：只写前 5 个 diff_*.txt", diffs == [f"diff_{i}.txt" for i in range(1, 6)], str(diffs))
    check("不一致：不写 fail_*.txt", not list(out3.glob("fail_*.txt")))

    body = (out3 / "diff_1.txt").read_text(encoding="utf-8")
    check("diff 文件：有复现命令，且带 --ref / --seed",
          "复现命令" in body and "--ref" in body and "--seed 11" in body)
    check("diff 文件：有输入数据", "3\n1 2 3" in body)
    check("diff 文件：有两边的输出",
          "被测试程序的输出" in body and "参考程序的输出" in body
          and "sum = 6" in body and "sum = 7" in body)
    check("diff 文件：写明了第一处不同在第几行第几列",
          re.search(r"第 1 行第 \d+ 列", body) is not None,
          (re.search(r"第 1 行第 \d+ 列", body) or ["(没找到)"])[0])

    # ---- 4. 参考程序崩了：算「参考程序出错」，不算被测试程序的错 ---------- #
    out4 = fresh("out4")
    proc = run_main(str(WORK / "t_ok.py"), "--ref", str(WORK / "r_crash.py"), count=6, outdir=out4)
    line, passed, crashed, timed_out, mismatch = stats_of(proc.stdout)
    check("参考程序崩了：被测试程序一组都没被判错（崩/不一致都是 0）",
          crashed == 0 and mismatch == 0, f"崩={crashed} 不一致={mismatch} 行={line!r}")
    check("参考程序崩了：统计行还是新格式（不一致 0 组）",
          line == "通过 0 组 / 崩 0 组 / 超时 0 组 / 不一致 0 组", repr(line))
    check("参考程序崩了：补了一句「参考程序自身出错 N 组，请先修参考程序」",
          f"参考程序自身出错 6 组，请先修参考程序" in proc.stdout, repr(proc.stdout.strip()[-40:]))
    check("参考程序崩了：不写 fail_*.txt / diff_*.txt",
          not list(out4.glob("fail_*.txt")) and not list(out4.glob("diff_*.txt")))
    ref_files = sorted(p.name for p in out4.glob("ref_fail_*.txt"))
    check("参考程序崩了：只写前 3 个 ref_fail_*.txt",
          ref_files == ["ref_fail_1.txt", "ref_fail_2.txt", "ref_fail_3.txt"], str(ref_files))
    ref_body = (out4 / "ref_fail_1.txt").read_text(encoding="utf-8")
    check("ref_fail 文件：写清了参考程序报了什么错、并声明不算被测试程序的错",
          "返回码 3" in ref_body and "不是被测试程序的错" in ref_body and "复现命令" in ref_body)

    # ---- 5. 参考程序超时：同样算「参考程序出错」 -------------------------- #
    out5 = fresh("out5")
    proc = run_main(str(WORK / "t_ok.py"), "--ref", str(WORK / "r_hang.py"),
                    count=2, timeout="1", outdir=out5)
    line, passed, crashed, timed_out, mismatch = stats_of(proc.stdout)
    check("参考程序超时：算参考程序出错，超时计数不会算到被测试程序头上",
          timed_out == 0 and crashed == 0 and mismatch == 0, repr(line))
    check("参考程序超时：ref_fail 文件里写的是超时",
          "超时" in (out5 / "ref_fail_1.txt").read_text(encoding="utf-8"))

    # ---- 6. 被测试程序崩了 / 超时：不跑参考程序，也不比对 ---------------- #
    marker = WORK / "ref_ran.txt"
    if marker.exists():
        marker.unlink()
    out6 = fresh("out6")
    proc = run_main(str(WORK / "t_crash.py"), "--ref", str(WORK / "r_marker.py"),
                    count=4, outdir=out6)
    line, passed, crashed, timed_out, mismatch = stats_of(proc.stdout)
    check("被测试程序崩了：照旧记崩溃（4 组全崩）", crashed == 4 and mismatch == 0, repr(line))
    check("被测试程序崩了：参考程序一次都没被启动", not marker.exists(),
          f"marker 存在={marker.exists()}")
    check("被测试程序崩了：照旧写 fail_*.txt", len(list(out6.glob("fail_*.txt"))) == 4)
    check("被测试程序崩了：fail 文件顶部也有复现命令",
          "复现命令" in (out6 / "fail_1.txt").read_text(encoding="utf-8"))

    out7 = fresh("out7")
    proc = run_main(str(WORK / "t_hang.py"), "--ref", str(WORK / "r_marker.py"),
                    count=2, timeout="1", outdir=out7)
    line, passed, crashed, timed_out, mismatch = stats_of(proc.stdout)
    check("被测试程序超时：照旧记超时，不跑参考程序",
          timed_out == 2 and mismatch == 0 and not marker.exists(), repr(line))

    # ---- 7. 第一处不同的定位 ---------------------------------------------- #
    out8 = fresh("out8")
    proc = run_main(str(WORK / "t_abc.py"), "--ref", str(WORK / "r_abd.py"),
                    count=1, outdir=out8)
    body = (out8 / "diff_1.txt").read_text(encoding="utf-8")
    position_line = next((ln for ln in body.splitlines() if ln.startswith("第 ")), "(没找到)")
    check("定位：同一行里第 3 个字符不同 -> 第 1 行第 3 列", "第 1 行第 3 列" in body, position_line)

    out9 = fresh("out9")
    proc = run_main(str(WORK / "t_two.py"), "--ref", str(WORK / "r_three.py"),
                    count=1, outdir=out9)
    body = (out9 / "diff_1.txt").read_text(encoding="utf-8")
    check("定位：行数不一样 -> 指出第 3 行被测试程序没有",
          "第 3 行" in body and "没有这一行" in body,
          next((ln for ln in body.splitlines() if ln.startswith("第 ")), "(没找到)"))

    # ---- 8. --ref 指向不存在的文件 ---------------------------------------- #
    proc = run_main(str(WORK / "t_ok.py"), "--ref", str(WORK / "根本没有这个文件.py"), count=1)
    check("--ref 文件不存在：退出码 2 且提示里写的是「参考程序」",
          proc.returncode == 2 and "找不到参考程序" in proc.stderr, repr(proc.stderr[-60:]))

    failed = [n for n, ok in _results if not ok]
    print("\n" + "=" * 60)
    print(f"对拍自检：{len(_results) - len(failed)} 项通过 / {len(failed)} 项失败")
    for name in failed:
        print("  FAILED: " + name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
