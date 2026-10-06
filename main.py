#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压力测试器（Windows + Python 3.12，只使用标准库）

用法
----
    python main.py 被测试程序.py
    python main.py 被测试程序.py --seed 123
    python main.py 被测试程序.py --count 500 --timeout 2
    python main.py 被测试程序.py --ref 参考程序.py        # 对拍：顺便查答案对不对

工作原理
--------
1. 从 gen.py 里取出 gen() 函数，每调用一次返回一个字符串，这个字符串就是一组完整输入；
2. 循环 count 次：生成一组数据 -> 单独启动一次被测试程序（数据从 stdin 喂进去）-> 记录结果；
   注意是“生成一组、跑一次、再生成下一组”，不是把所有数据拼起来一次喂进去；
3. 判定标准：
       返回码非 0        -> 崩溃
       运行超过 timeout  -> 超时（默认 1 秒）
       返回码 0          -> 通过
   不给 --ref 时，行为就是上面这样，只在这三种之间判定。

对拍（给了 --ref 参考程序.py）
------------------------------
   每一组数据会同时喂给「被测试程序」和「参考程序」，然后比 stdout：

       被测试程序崩了 / 超时      -> 照旧记 崩溃 / 超时（这一组不比对）
       参考程序崩了 / 超时        -> 记「参考程序出错」，单独计数，
                                   绝对不算成被测试程序错了（免得你去改一个本来没错的程序）
       两边都正常退出（返回码 0） -> 比 stdout：一样记「通过」，不一样记「答案不一致」

   比输出时忽略：每行行尾空白、输出末尾的空行、行尾的 \r。

输出文件
--------
   fail_1.txt … fail_5.txt          最先崩的 5 组：输入 + 被测试程序的报错信息
   diff_1.txt … diff_5.txt          最先对不上的 5 组：输入 + 两边输出 + 第一处不同在第几行第几列
   ref_fail_1.txt … ref_fail_3.txt  最先出错的 3 组「参考程序自身出错」
   每个文件顶部都有一行「复现命令」，照着复制就能把这一批数据重新跑出来。

统计行
------
   不给 --ref：  通过 x 组 / 崩 n 组 / 超时 m 组
   给了 --ref：  通过 x 组 / 崩 n 组 / 超时 m 组 / 不一致 k 组
                 若参考程序出过错，下面再补一句：参考程序自身出错 j 组，请先修参考程序

随机种子与可复现
----------------
    --seed 123 会让本程序给全局 random 模块播种，并把 SEED、rnd 注入 gen 模块；
    因此同一个种子、同一台机器上，每次生成的 count 组数据完全一致。
    不加 --seed 时会随机挑一个种子，并把它打印出来，用那个种子重跑即可复现。

退出码
------
    0 = 全部通过
    1 = 出现了崩溃 / 超时 / 答案不一致 / 参考程序出错
        （最后一种会在统计行下面单独说明，它不代表被测试程序有错）
    2 = 用法/环境错误（被测试程序、参考程序、gen.py、gen() 有问题等）
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import random
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_COUNT = 200
DEFAULT_TIMEOUT = 1.0
MAX_FAIL_FILES = 5
MAX_DIFF_FILES = 5
MAX_REF_FAIL_FILES = 3

STATUS_PASS = "通过"
STATUS_CRASH = "崩溃"
STATUS_TIMEOUT = "超时"
STATUS_MISMATCH = "不一致"          # 对拍时两边输出不一样
STATUS_REF_ERROR = "参考程序出错"    # 参考程序自己崩了/超时，不算被测试程序的错

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_USAGE = 2

GEN_MODULE_NAME = "dsh_stress_gen"

# 正在跑的那个子进程，只用来在 Ctrl+C 中断时收尾，别把它留在后台。
_current_proc = None


class FatalError(Exception):
    """用法或者环境层面的错误：打印一句人话，然后退出。"""


# --------------------------------------------------------------------------- #
# 命令行
# --------------------------------------------------------------------------- #
def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Python 程序压力测试器：随机生成大量输入，逐组单独运行被测试程序，最后报告出问题的数据。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例子:\n"
            "  python main.py example_target.py\n"
            "  python main.py example_target.py --seed 123\n"
            "  python main.py my_prog.py --count 500 --timeout 2 --gen my_gen.py\n"
            "  python main.py my_prog.py --ref brute.py --seed 123      # 对拍\n"
        ),
    )
    parser.add_argument("target", help="被测试的 .py 文件")
    parser.add_argument("--ref", default=None, metavar="参考程序.py",
                        help="参考程序（对拍用）：每组数据同时喂给它，再比较两边的 stdout；"
                             "不给就只做压力测试")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, metavar="N",
                        help=f"测试组数（默认 {DEFAULT_COUNT}）")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="秒",
                        help=f"单组超时时间，单位秒（默认 {DEFAULT_TIMEOUT}）")
    parser.add_argument("--seed", type=int, default=None, metavar="N",
                        help="随机种子；给同一个种子，每次生成的 N 组数据完全一样")
    parser.add_argument("--gen", default=None, metavar="路径",
                        help="数据生成规则文件（默认依次找：main.py 同目录的 gen.py、被测试程序同目录的 gen.py）")
    parser.add_argument("--outdir", default=None, metavar="目录",
                        help="失败数据的输出目录（默认当前目录）")
    parser.add_argument("--python", dest="python_exe", default=None, metavar="解释器",
                        help="用哪个解释器运行被测试程序（默认当前解释器）")
    parser.add_argument("--quiet", action="store_true",
                        help="不打印每一组的进度，只打印结尾统计")

    args = parser.parse_args(argv)
    if args.count < 1:
        raise FatalError("--count 至少是 1")
    if args.timeout <= 0:
        raise FatalError("--timeout 必须大于 0")
    return args


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def make_output_safe() -> None:
    """控制台编码不支持某个字符时用 ? 代替，不要让打印本身把程序搞崩。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def log(message: str = "") -> None:
    print(message, flush=True)


def short_hint(output: str) -> str:
    """从输出里取最后一行非空内容，当作失败原因提示。"""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line:
            return line if len(line) <= 80 else line[:77] + "..."
    return ""


# --------------------------------------------------------------------------- #
# 路径与 gen.py
# --------------------------------------------------------------------------- #
def resolve_target(raw: str, role: str = "被测试程序") -> Path:
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.resolve()
    if not target.exists():
        raise FatalError(f"找不到{role}：{target}")
    if not target.is_file():
        raise FatalError(f"{role}不是一个文件：{target}")
    if target.suffix.lower() != ".py":
        raise FatalError(f"{role}必须是 .py 文件：{target}")
    return target


def find_gen_file(explicit: str | None, target: Path, main_dir: Path) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        if not path.is_file():
            raise FatalError(f"找不到数据生成规则文件：{path}")
        return path

    candidates = [main_dir / "gen.py", target.parent / "gen.py", Path.cwd() / "gen.py"]
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate.resolve()

    looked = "\n  ".join(str(c) for c in candidates)
    raise FatalError(
        "找不到 gen.py（数据生成规则文件）。已经找过这些位置：\n  "
        + looked
        + "\n可以用 --gen 指定它在哪里。"
    )


def load_generator(gen_path: Path, seed: int):
    """加载 gen.py，返回里面的 gen() 函数。"""
    gen_dir = str(gen_path.parent)
    if gen_dir not in sys.path:
        sys.path.insert(0, gen_dir)

    spec = importlib.util.spec_from_file_location(GEN_MODULE_NAME, str(gen_path))
    if spec is None or spec.loader is None:
        raise FatalError(f"无法加载数据生成规则文件：{gen_path}")

    module = importlib.util.module_from_spec(spec)
    previous_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True   # 别在用户目录里留下 __pycache__
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise FatalError(f"执行 {gen_path.name} 时出错：{exc!r}") from exc
    finally:
        sys.dont_write_bytecode = previous_flag

    gen_fn = getattr(module, "gen", None)
    if not callable(gen_fn):
        raise FatalError(f"{gen_path} 里面没有找到可调用的 gen() 函数")

    # 注入随机源：这样 --seed 才能真正决定 gen() 生成什么数据。
    module.SEED = seed
    module.rnd = random.Random(seed)
    return gen_fn


def generate_one(gen_fn, index: int) -> str:
    try:
        data = gen_fn()
    except Exception as exc:
        raise FatalError(f"生成第 {index} 组数据时出错：{exc!r}") from exc

    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    elif not isinstance(data, str):
        data = str(data)
    return data


# --------------------------------------------------------------------------- #
# 运行被测试程序
# --------------------------------------------------------------------------- #
def build_child_env() -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"   # 子进程的 stdin/stdout 统一成 utf-8，避免中文乱码
    env["PYTHONHASHSEED"] = "0"         # 固定哈希随机化，同一个种子跑出来的行为一致
    return env


def kill_process_tree(proc: subprocess.Popen) -> None:
    """超时后干掉被测试程序，并且尽量连它自己起的子进程一起收掉。

    Windows 上先试 taskkill /T（普通控制台里能把整棵进程树杀掉）；
    不管 taskkill 成不成功，最后都对直接子进程再 kill() 一次，双保险。
    """
    if proc.poll() is None and os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except Exception:
            pass
    try:
        proc.kill()   # 进程已经退出时 Popen 会自己跳过，随便调
    except Exception:
        pass


def drain_after_kill(proc: subprocess.Popen, grace: float = 1.0) -> str:
    """把已经产生的输出收上来，但最多等 grace 秒。

    被测试程序如果自己又起了子进程，那些孙子进程会继承 stdout 管道；
    这时就算目标进程已经死了，管道也不会关闭，communicate() 会一直等下去。
    所以这里等不到就走人，不能让每一组超时都白等十几秒。

    注意：这里刻意不去 close(proc.stdout)。communicate() 超时后在后台留了一个
    读管道的线程，它握着缓冲区上的锁，close() 会一直等那把锁，等于又等回原地。
    那个线程是 daemon 线程，不会拖住程序退出，直接不管它就行。
    """
    try:
        output, _ = proc.communicate(timeout=grace)
        return output or ""
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    try:
        proc.wait(timeout=1)   # 只等进程句柄，不碰管道
    except Exception:
        pass
    return ""


def run_target(cmd: list[str], cwd: Path, env: dict, data: str, timeout: float):
    """跑一次被测试程序，返回 (是否超时, 返回码, 全部输出, 耗时秒)。"""
    global _current_proc
    started = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,   # 报错信息也要收上来，写进 fail_*.txt
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    _current_proc = proc
    try:
        try:
            output, _ = proc.communicate(data, timeout=timeout)
            return False, proc.returncode, output or "", time.perf_counter() - started
        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - started
            kill_process_tree(proc)
            output = drain_after_kill(proc)
            return True, None, output, elapsed
    finally:
        _current_proc = None


# --------------------------------------------------------------------------- #
# 对拍：比较两个程序的输出
# --------------------------------------------------------------------------- #
def normalize_lines(text: str) -> list[str]:
    """按对拍规则归一化：忽略每行行尾空白、行尾的 \\r、以及输出末尾的空行。"""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def compare_outputs(tested: str, reference: str):
    """比 stdout。返回 (是否一致, 第一处不同的说明, (被测试那一行, 参考那一行))。"""
    a = normalize_lines(tested)
    b = normalize_lines(reference)
    for i in range(max(len(a), len(b))):
        la = a[i] if i < len(a) else None
        lb = b[i] if i < len(b) else None
        if la == lb:
            continue
        # 走到这里就是第一处不同
        if la is None:
            return False, f"第 {i + 1} 行：被测试程序没有这一行（参考程序是 {lb!r}）", (None, lb)
        if lb is None:
            return False, f"第 {i + 1} 行：参考程序没有这一行（被测试程序是 {la!r}）", (la, None)
        column = next((j + 1 for j, (ca, cb) in enumerate(zip(la, lb)) if ca != cb),
                      min(len(la), len(lb)) + 1)
        return False, f"第 {i + 1} 行第 {column} 列", (la, lb)
    return True, "（没有差异）", ("", "")


def build_repro_command(main_py: Path, python_exe: str, target: Path, gen_path: Path,
                        count: int, timeout: float, seed: int, ref=None) -> str:
    """拼一行「复制到命令行就能把这一批数据重跑一遍」的复现命令。"""
    def quote(value) -> str:
        text = str(value)
        return f'"{text}"' if (" " in text or "\t" in text) else text

    interpreter = Path(python_exe)
    python_part = "python" if interpreter.stem.lower().startswith("python") else quote(python_exe)

    parts = [python_part, quote(main_py), quote(target),
             "--gen", quote(gen_path),
             "--count", str(count), "--timeout", str(timeout), "--seed", str(seed)]
    if ref is not None:
        parts += ["--ref", quote(ref)]
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# 失败数据落盘
# --------------------------------------------------------------------------- #
def write_fail_file(path: Path, index: int, data: str, output: str,
                    returncode, elapsed: float, seed: int, target: Path, repro: str) -> None:
    lines = [
        "=" * 66,
        f"压力测试失败记录：第 {index} 组数据（崩溃）",
        f"复现命令  : {repro}",
        f"被测试程序: {target}",
        f"随机种子  : {seed}    （用 --seed {seed} 可以复现这一组）",
        f"返回码    : {returncode}",
        f"耗时      : {elapsed:.3f} 秒",
        "=" * 66,
        "",
        "---------- 输入数据（完整喂给被测试程序的 stdin）----------",
        data,
        "",
        "---------- 被测试程序的输出 / 报错信息 ----------",
        output if output.strip() else "(没有任何输出)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_diff_file(path: Path, index: int, data: str,
                    tested_output: str, ref_output: str,
                    tested_rc, tested_elapsed: float,
                    ref_rc, ref_elapsed: float,
                    where: str, diff_lines, seed: int,
                    target: Path, ref: Path, repro: str) -> None:
    tested_line, ref_line = diff_lines
    a_lines = normalize_lines(tested_output)
    b_lines = normalize_lines(ref_output)

    def show(value) -> str:
        return "(没有这一行)" if value is None else value

    lines = [
        "=" * 66,
        f"答案不一致记录：第 {index} 组数据（对拍失败）",
        f"复现命令  : {repro}",
        f"被测试程序: {target}",
        f"参考程序  : {ref}",
        f"随机种子  : {seed}",
        f"被测试结果: 返回码 {tested_rc}，耗时 {tested_elapsed:.3f} 秒",
        f"参考结果  : 返回码 {ref_rc}，耗时 {ref_elapsed:.3f} 秒",
        "=" * 66,
        "",
        "---------- 输入数据（同一份数据喂给两个程序）----------",
        data,
        "",
        "---------- 第一处不同 ----------",
        f"{where}    （被测试程序 {len(a_lines)} 行 / 参考程序 {len(b_lines)} 行；"
        "比较时已忽略行尾空白、行尾的 \\r、输出末尾的空行）",
        f"  被测试程序: {show(tested_line)}",
        f"  参考程序  : {show(ref_line)}",
        "",
        "---------- 被测试程序的输出 ----------",
        tested_output if tested_output.strip() else "(没有任何输出)",
        "",
        "---------- 参考程序的输出 ----------",
        ref_output if ref_output.strip() else "(没有任何输出)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_ref_fail_file(path: Path, index: int, data: str,
                        ref_output: str, ref_rc, ref_elapsed: float, ref_timeout: bool,
                        tested_rc, tested_elapsed: float, timeout: float, seed: int,
                        target: Path, ref: Path, repro: str) -> None:
    ref_result = (f"超时（超过 {timeout} 秒，已被杀掉）" if ref_timeout
                  else f"返回码 {ref_rc}")
    lines = [
        "=" * 66,
        f"参考程序出错记录：第 {index} 组数据",
        "注意：这是参考程序自己崩了/超时，不是被测试程序的错，不要照着它去改被测试程序。",
        f"复现命令  : {repro}",
        f"被测试程序: {target}",
        f"参考程序  : {ref}",
        f"随机种子  : {seed}",
        f"参考程序结果  : {ref_result}，耗时 {ref_elapsed:.3f} 秒",
        f"被测试程序这组是正常的: 返回码 {tested_rc}，耗时 {tested_elapsed:.3f} 秒",
        "=" * 66,
        "",
        "---------- 输入数据 ----------",
        data,
        "",
        "---------- 参考程序的输出 / 报错信息 ----------",
        ref_output if ref_output.strip() else "(没有任何输出)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    make_output_safe()

    try:
        args = parse_args(argv)
        main_dir = Path(__file__).resolve().parent
        target = resolve_target(args.target)
        ref = resolve_target(args.ref, "参考程序") if args.ref is not None else None
        gen_path = find_gen_file(args.gen, target, main_dir)
        outdir = Path(args.outdir).expanduser() if args.outdir else Path.cwd()
        outdir = outdir.resolve()
        outdir.mkdir(parents=True, exist_ok=True)
    except FatalError as exc:
        print(f"错误：{exc}", file=sys.stderr, flush=True)
        return EXIT_USAGE

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1, 2 ** 31 - 1)
    random.seed(seed)   # 让 gen.py 里直接用 random 的写法也可以复现

    try:
        gen_fn = load_generator(gen_path, seed)
    except FatalError as exc:
        print(f"错误：{exc}", file=sys.stderr, flush=True)
        return EXIT_USAGE

    python_exe = args.python_exe or sys.executable
    cmd = [python_exe, str(target)]
    ref_cmd = [python_exe, str(ref)] if ref is not None else None
    env = build_child_env()

    # 每个失败文件顶部都会写上这一行，照着复制就能重现这批数据
    repro = build_repro_command(Path(__file__).resolve(), python_exe, target, gen_path,
                                args.count, args.timeout, seed, ref)

    log("=" * 66)
    log("Python 压力测试器")
    log(f"  被测试程序  : {target}")
    if ref is not None:
        log(f"  参考程序    : {ref}      （对拍模式：两个程序都跑，比 stdout）")
    log(f"  数据生成规则: {gen_path}")
    log(f"  运行解释器  : {python_exe}")
    log(f"  测试组数    : {args.count} 组      单组超时: {args.timeout} 秒")
    log(f"  随机种子    : {seed}" + ("（--seed 指定）" if args.seed is not None
                                     else f"（随机；复现请加 --seed {seed}）"))
    log(f"  失败数据目录: {outdir}")
    log("=" * 66)
    if ref is not None and ref == target:
        log("提示：参考程序和被测试程序是同一个文件，对拍结果必然一致。")

    counts = {STATUS_PASS: 0, STATUS_CRASH: 0, STATUS_TIMEOUT: 0,
              STATUS_MISMATCH: 0, STATUS_REF_ERROR: 0}
    saved = 0
    saved_diff = 0
    saved_ref = 0
    fail_notes: list[str] = []
    diff_notes: list[str] = []
    ref_notes: list[str] = []

    for index in range(1, args.count + 1):
        try:
            data = generate_one(gen_fn, index)
        except FatalError as exc:
            print(f"错误：{exc}", file=sys.stderr, flush=True)
            return EXIT_USAGE

        try:
            hit_timeout, returncode, output, elapsed = run_target(
                cmd, target.parent, env, data, args.timeout
            )
        except OSError as exc:
            print(f"错误：启动不了被测试程序：{exc}", file=sys.stderr, flush=True)
            return EXIT_USAGE

        if hit_timeout:
            status = STATUS_TIMEOUT
        elif returncode != 0:
            status = STATUS_CRASH
        else:
            status = STATUS_PASS

        # —— 只有被测试程序正常退出，才跑参考程序来对拍 ——
        ref_timeout = False
        ref_returncode = None
        ref_output = ""
        ref_elapsed = 0.0
        where = ""
        diff_lines = ("", "")
        if status == STATUS_PASS and ref_cmd is not None:
            try:
                ref_timeout, ref_returncode, ref_output, ref_elapsed = run_target(
                    ref_cmd, ref.parent, env, data, args.timeout
                )
            except OSError as exc:
                print(f"错误：启动不了参考程序：{exc}", file=sys.stderr, flush=True)
                return EXIT_USAGE

            if ref_timeout or ref_returncode != 0:
                # 参考程序自己的问题：单独计数，绝不算是被测试程序错了
                status = STATUS_REF_ERROR
            else:
                same, where, diff_lines = compare_outputs(output, ref_output)
                if not same:
                    status = STATUS_MISMATCH

        counts[status] += 1

        if not args.quiet:
            width = 6 if ref_cmd is not None else 3
            line = f"[{index:>4}/{args.count}] {status:<{width}} {elapsed:7.3f}s"
            if status == STATUS_CRASH:
                line += f"  返回码={returncode}"
            hint = ""
            if status == STATUS_MISMATCH:
                left = diff_lines[0] if diff_lines[0] is not None else "(没有这一行)"
                right = diff_lines[1] if diff_lines[1] is not None else "(没有这一行)"
                hint = f"{where}  被测试={str(left)[:24]!r} 参考={str(right)[:24]!r}"
            elif status == STATUS_REF_ERROR:
                ref_state = "超时" if ref_timeout else f"返回码={ref_returncode}"
                ref_hint = short_hint(ref_output)
                hint = f"参考程序 {ref_state}" + (f"  {ref_hint}" if ref_hint else "")
            elif status != STATUS_PASS:
                hint = short_hint(output)
            if hint:
                line += f"  {hint}"
            log(line)

        if status == STATUS_CRASH and saved < MAX_FAIL_FILES:
            saved += 1
            fail_path = outdir / f"fail_{saved}.txt"
            try:
                write_fail_file(fail_path, index, data, output, returncode, elapsed,
                                seed, target, repro)
            except OSError as exc:
                saved -= 1
                print(f"警告：写不进 {fail_path}：{exc}", file=sys.stderr, flush=True)
            else:
                fail_notes.append(f"{fail_path.name} <- 第 {index} 组")
                if not args.quiet:
                    log(f"          -> 已保存 {fail_path.name}（第 {index} 组）")

        elif status == STATUS_MISMATCH and saved_diff < MAX_DIFF_FILES:
            saved_diff += 1
            diff_path = outdir / f"diff_{saved_diff}.txt"
            try:
                write_diff_file(diff_path, index, data, output, ref_output,
                                returncode, elapsed, ref_returncode, ref_elapsed,
                                where, diff_lines, seed, target, ref, repro)
            except OSError as exc:
                saved_diff -= 1
                print(f"警告：写不进 {diff_path}：{exc}", file=sys.stderr, flush=True)
            else:
                diff_notes.append(f"{diff_path.name} <- 第 {index} 组（{where}）")
                if not args.quiet:
                    log(f"          -> 已保存 {diff_path.name}（第 {index} 组）")

        elif status == STATUS_REF_ERROR and saved_ref < MAX_REF_FAIL_FILES:
            saved_ref += 1
            ref_fail_path = outdir / f"ref_fail_{saved_ref}.txt"
            try:
                write_ref_fail_file(ref_fail_path, index, data, ref_output,
                                    ref_returncode, ref_elapsed, ref_timeout,
                                    returncode, elapsed, args.timeout, seed,
                                    target, ref, repro)
            except OSError as exc:
                saved_ref -= 1
                print(f"警告：写不进 {ref_fail_path}：{exc}", file=sys.stderr, flush=True)
            else:
                ref_notes.append(f"{ref_fail_path.name} <- 第 {index} 组")
                if not args.quiet:
                    log(f"          -> 已保存 {ref_fail_path.name}（第 {index} 组）")

    passed = counts[STATUS_PASS]
    crashed = counts[STATUS_CRASH]
    timed_out = counts[STATUS_TIMEOUT]
    mismatched = counts[STATUS_MISMATCH]
    ref_errors = counts[STATUS_REF_ERROR]

    log("-" * 66)
    if fail_notes:
        log(f"前 {MAX_FAIL_FILES} 组崩溃数据已保存：")
        for note in fail_notes:
            log(f"  {note}")
    if diff_notes:
        log(f"前 {MAX_DIFF_FILES} 组答案不一致数据已保存：")
        for note in diff_notes:
            log(f"  {note}")
    if ref_notes:
        log(f"前 {MAX_REF_FAIL_FILES} 组参考程序出错数据已保存：")
        for note in ref_notes:
            log(f"  {note}")
    if not (fail_notes or diff_notes or ref_notes) and crashed == 0:
        log("没有崩溃数据需要保存。")

    if ref_cmd is None:
        # 不给 --ref 时，统计行和以前一模一样
        log(f"通过 {passed} 组 / 崩 {crashed} 组 / 超时 {timed_out} 组")
    else:
        log(f"通过 {passed} 组 / 崩 {crashed} 组 / 超时 {timed_out} 组 / 不一致 {mismatched} 组")
        if ref_errors:
            log(f"参考程序自身出错 {ref_errors} 组，请先修参考程序")

    bad = crashed + timed_out + mismatched + ref_errors
    return EXIT_OK if bad == 0 else EXIT_FAILURES


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        if _current_proc is not None:
            kill_process_tree(_current_proc)
        print("\n已被用户中断。", file=sys.stderr, flush=True)
        sys.exit(130)
