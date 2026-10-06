# -*- coding: utf-8 -*-
"""图形界面自检：真的把 app.py 的界面建起来、跑一遍、再停一次。

用法：
    python _selftest/gui_check.py

窗口是隐藏的（root.withdraw()），不会打扰你，但界面逻辑是真的在跑。
"""

import ctypes
import os
import re
import shutil
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import app as app_module  # noqa: E402

WORK = HERE / "gui_work"
OUT = HERE / "gui_out"
STATS_RE = re.compile(r"^通过 \d+ 组 / 崩 \d+ 组 / 超时 \d+ 组$")

_results = []


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("   -> " + detail) if detail else ""), flush=True)
    return bool(ok)


def skip(name, detail=""):
    print("SKIP  " + name + (("   -> " + detail) if detail else ""), flush=True)


def pump(root, seconds, until=None):
    """在等待期间不断处理界面事件，模拟真实的界面刷新。"""
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if until is not None and until():
            return True
        time.sleep(0.02)
    return (until() if until is not None else True)


def pid_alive(pid):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == 259
    finally:
        kernel32.CloseHandle(handle)


def taskkill_works_here():
    victim = __import__("subprocess").Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        time.sleep(0.3)
        import subprocess as sp
        r = sp.run(["taskkill", "/F", "/PID", str(victim.pid)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
        return (r.returncode == 0 and not pid_alive(victim.pid)), (r.stdout + r.stderr).strip()
    finally:
        try:
            victim.kill()
            victim.wait(timeout=5)
        except Exception:
            pass


def prepare():
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("fail_*.txt"):
        old.unlink()
    (WORK / "hang.py").write_text(
        "import os, time\nfrom pathlib import Path\n"
        f"Path(r'{WORK / 'hang_pid.txt'}').write_text(str(os.getpid()), encoding='utf-8')\n"
        "print('start', flush=True)\ntime.sleep(300)\n",
        encoding="utf-8",
    )


def run_checks():
    prepare()
    target = ROOT / "example_target.py"
    hang = WORK / "hang.py"
    hang_pid_file = WORK / "hang_pid.txt"

    root = tk.Tk()
    root.withdraw()                      # 隐藏窗口，别打扰正在用电脑的人
    application = app_module.StressApp(root)
    warnings = []
    app_module.messagebox.showwarning = lambda *a, **k: warnings.append(a)
    app_module.messagebox.showerror = lambda *a, **k: warnings.append(a)
    app_module.messagebox.askyesno = lambda *a, **k: True

    # ---- 1. 界面元素齐全 -------------------------------------------------- #
    check("界面：开始/停止按钮都在", hasattr(application, "start_btn") and hasattr(application, "stop_btn"))
    check("界面：日志区、gen 编辑器、失败列表都在",
          all(hasattr(application, n) for n in ("log_text", "gen_text", "fail_list", "stats_label")))
    check("界面：main.py 找对了", application.main_py.name == "main.py" and application.main_py.is_file(),
          str(application.main_py))
    check("界面：初始状态是空闲，停止按钮不可点",
          str(application.stop_btn["state"]) == "disabled" and application.running is False)

    # ---- 2. gen.py 编辑与保存 -------------------------------------------- #
    # 注意：下面的操作会让界面以为 gen.py 有改动；跑正式测试前必须把编辑器恢复成
    # 真正 gen.py 的内容，否则 app 的"开始前自动保存"会把临时内容写回 gen.py。
    real_gen_text = (ROOT / "gen.py").read_text(encoding="utf-8")
    tmp_gen = WORK / "gen_roundtrip.py"
    application.gen_py = tmp_gen
    application.gen_text.delete("1.0", "end")
    application.gen_text.insert("1.0", "import random\n\n\ndef gen():\n    return '%d\\n' % random.randint(1, 9)\n")
    application.gen_dirty = True
    saved_ok = application.save_gen()
    check("gen.py：界面上改完能存盘", saved_ok and "random.randint" in tmp_gen.read_text(encoding="utf-8"))
    check("gen.py：保存后不会再提示未保存", application.gen_dirty is False)
    application.gen_py = ROOT / "gen.py"
    application.load_gen()                       # 把编辑器恢复成真正的 gen.py
    check("gen.py：编辑器恢复后内容和磁盘一致",
          application.gen_text.get("1.0", "end-1c") == real_gen_text and application.gen_dirty is False)

    # ---- 3. 输入校验（不应该真的启动进程） -------------------------------- #
    application.target_var.set(str(target))
    application.count_var.set("不是数字")
    application.start()
    check("校验：组数填错时给提示且不启动",
          bool(warnings) and application.running is False and application.proc is None)
    application.count_var.set("10")
    application.timeout_var.set("0")
    warnings.clear()
    application.start()
    check("校验：超时填 0 时给提示且不启动", bool(warnings) and application.proc is None)
    application.timeout_var.set("1.0")
    application.seed_var.set("abc")
    warnings.clear()
    application.start()
    check("校验：种子不是整数时给提示且不启动", bool(warnings) and application.proc is None)

    # ---- 4. 正常跑一轮：不卡界面、实时出日志、统计醒目显示 --------------- #
    application.outdir = OUT
    application.outdir_var.set(str(OUT))
    application.seed_var.set("123")
    application.count_var.set("10")
    warnings.clear()
    application.start()
    check("运行：点开始后立刻进入运行态", application.running is True)

    streamed_while_running = False
    started = time.time()
    while time.time() - started < 90:
        root.update()
        lines = int(application.log_text.index("end-1c").split(".")[0])
        if application.running and lines >= 4:
            streamed_while_running = True      # 还在跑就已经有日志了 = 真的在流式刷新
        if not application.running:
            break
        time.sleep(0.02)
    elapsed = time.time() - started
    pump(root, 0.8)

    check("运行：10 组跑完并回到空闲", application.running is False and application.proc is None,
          f"{elapsed:.2f}s")
    check("运行：跑到一半界面就已经在刷新日志（没有卡死）", streamed_while_running)
    check("运行：统计行被单独抓出来显示",
          STATS_RE.match(application.stats_text) is not None, repr(application.stats_text))
    check("运行：醒目的统计标签和统计行一致",
          application.stats_label["text"] == application.stats_text, repr(application.stats_label["text"]))
    check("运行：结束后开始按钮恢复、停止按钮禁用",
          str(application.start_btn["state"]) == "normal" and str(application.stop_btn["state"]) == "disabled")

    log_body = application.log_text.get("1.0", "end")
    check("运行：日志里有第 1 组和第 10 组的进度行",
          "[   1/10]" in log_body and "[  10/10]" in log_body)
    check("运行：日志里有中文判定字样", ("通过" in log_body) or ("崩溃" in log_body))

    listed = [p for p in application.current_fails if p is not None]
    check("失败用例：列出了这次生成的 fail_*.txt", len(listed) >= 1 and all(p.is_file() for p in listed),
          f"{[p.name for p in listed]}")
    check("失败用例：列表里真的显示出了这几行",
          application.fail_list.size() == len(listed),
          f"listbox={application.fail_list.size()} paths={len(listed)}")

    # ---- 5. 点一下能打开（而且只打开一次） -------------------------------- #
    check("失败用例：没有绑双击（双击=两次单击，会重复打开）",
          not application.fail_list.bind("<Double-Button-1>"),
          repr(application.fail_list.bind("<Double-Button-1>")))

    opened = []
    application.open_path = lambda p: opened.append(p)
    application.fail_list.selection_clear(0, "end")
    application.fail_list.selection_set(0)
    application.open_selected_fail()
    check("失败用例：点一下会调用系统默认程序打开它",
          len(opened) == 1 and opened[0] == listed[0], str(opened))

    # 真实双击会被系统拆成两次单击事件，所以要保证第二次不会又打开一遍
    application.open_selected_fail()
    application.open_selected_fail()
    check("失败用例：连点两次同一个文件只打开一次", len(opened) == 1, str(opened))

    # 没有失败文件时点占位行不应该出错
    application.current_fails = [None]
    application.fail_list.delete(0, "end")
    application.fail_list.insert("end", "（这次没有产生 fail_*.txt）")
    application.fail_list.selection_set(0)
    opened.clear()
    application.open_selected_fail()
    check("失败用例：没有文件时点占位行不会报错、也不会打开东西", not opened)

    # 打开失败时给的提示必须是"人话"，并且带完整路径
    def boom(_p):
        raise OSError("[WinError 5] 拒绝访问")

    errs = []
    app_module.messagebox.showerror = lambda *a, **k: errs.append(a)
    original_open_with_system = app_module.open_with_system
    app_module.open_with_system = boom
    miss = ROOT / "_selftest" / "根本不存在_fail_1.txt"
    try:
        app_module.StressApp.open_path(application, miss)     # 调真实的 open_path
    finally:
        app_module.open_with_system = original_open_with_system
    text = " ".join(str(x) for x in errs[-1]) if errs else ""
    check("打开失败：提示是人话、带完整路径、不甩系统报错原文",
          bool(errs) and "安全软件" in text and "记事本" in text
          and str(miss) in text and "WinError" not in text,
          text[:70])

    # ---- 6. 停止：杀进程在后台，主线程不等人 ------------------------------ #
    tree_ok, tree_detail = taskkill_works_here()
    if hang_pid_file.exists():
        hang_pid_file.unlink()
    application.target_var.set(str(hang))
    application.count_var.set("50")
    application.timeout_var.set("5")
    application.seed_var.set("")
    warnings.clear()
    application.start()
    check("停止：挂住的程序已经开始跑", application.running is True)
    pump(root, 1.5)

    # 把「杀进程」故意换成慢动作，验证 stop() 不会堵住主线程
    real_kill = app_module.StressApp.kill_tree
    killed = []

    def slow_kill(proc):
        time.sleep(2.5)                 # 模拟 taskkill 卡住
        killed.append(proc)
        real_kill(proc)

    app_module.StressApp.kill_tree = staticmethod(slow_kill)
    t0 = time.time()
    try:
        application.stop()
        call_elapsed = time.time() - t0
        ticks = 0
        while not killed and time.time() - t0 < 8:
            root.update()
            ticks += 1
            time.sleep(0.02)
        check("停止：杀进程放到后台线程，stop() 立刻返回（不等 taskkill）",
              call_elapsed < 0.3, f"stop() 只用了 {call_elapsed:.3f}s")
        check("停止：后台慢慢杀进程的这段时间里，界面一直在刷新",
              ticks > 20, f"刷新了 {ticks} 次")
    finally:
        app_module.StressApp.kill_tree = staticmethod(real_kill)

    pump(root, 15, until=lambda: application.running is False)
    stop_elapsed = time.time() - t0
    check("停止：点停止后很快回到空闲（没有被卡住）",
          application.running is False and stop_elapsed < 10, f"{stop_elapsed:.2f}s")
    check("停止：状态显示成已停止", application.status_var.get() == "已停止",
          repr(application.status_var.get()))
    check("停止：停止按钮又变灰了", str(application.stop_btn["state"]) == "disabled")

    if hang_pid_file.exists():
        hang_pid = int(hang_pid_file.read_text(encoding="utf-8"))
        time.sleep(0.8)
        alive = pid_alive(hang_pid)
        if alive:
            # 环境限制：这里 taskkill 被拒绝，被测试进程是 main.py 的孙子进程，收不掉
            if tree_ok:
                check("停止：被测试进程也一起被结束了", False, f"pid {hang_pid} 还活着")
            else:
                skip("停止：被测试进程也一起被结束了",
                     f"本环境禁止 taskkill（{tree_detail}），普通控制台下才能验证")
            app_module.StressApp.kill_tree(application.proc) if application.proc else None
            import subprocess as sp
            sp.run(["taskkill", "/F", "/PID", str(hang_pid)],
                   stdout=sp.DEVNULL, stderr=sp.DEVNULL, check=False)
        else:
            check("停止：被测试进程也一起被结束了", True)
    else:
        skip("停止：被测试进程也一起被结束了", "没拿到被测试进程 pid")

    # ---- 7. 关窗 ----------------------------------------------------------- #
    application.on_close()
    check("关窗：窗口正常销毁", True)

    failed = [n for n, ok in _results if not ok]
    print("\n" + "=" * 60)
    print(f"界面自检：{len(_results) - len(failed)} 项通过 / {len(failed)} 项失败")
    for name in failed:
        print("  FAILED: " + name)
    return 1 if failed else 0


def main():
    """跑自检，并且无论如何都把 gen.py 还原成运行前的样子（自检不该改交付物）。"""
    gen_py = ROOT / "gen.py"
    original = gen_py.read_text(encoding="utf-8")
    try:
        return run_checks()
    finally:
        if gen_py.read_text(encoding="utf-8") != original:
            gen_py.write_text(original, encoding="utf-8")
            print("（自检改动了 gen.py，已还原）", flush=True)


if __name__ == "__main__":
    sys.exit(main())
