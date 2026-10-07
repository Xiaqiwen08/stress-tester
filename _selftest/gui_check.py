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
    check("界面：有「参考程序」输入框（对拍用）",
          hasattr(application, "ref_var") and application.ref_var.get() == "")
    check("界面：窗口标题带版本号",
          app_module.APP_VERSION == "0.2.0"
          and f"v{app_module.APP_VERSION}" in root.title(), repr(root.title()))
    check("界面：日志开头也写了版本号",
          f"v{app_module.APP_VERSION}" in application.log_text.get("1.0", "end"))
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

    # ---- 5. 点一下在界面内预览 -------------------------------------------- #
    check("失败用例：没有绑双击（双击=两次单击，会重复打开）",
          not application.fail_list.bind("<Double-Button-1>"),
          repr(application.fail_list.bind("<Double-Button-1>")))

    opened = []
    application.open_preview = lambda p: opened.append(p)
    application.fail_list.selection_clear(0, "end")
    application.fail_list.selection_set(0)
    application.open_selected_fail()
    check("失败用例：点一下会去预览这个文件",
          len(opened) == 1 and opened[0] == listed[0], str(opened))

    # 没有失败文件时点占位行不应该出错
    application.current_fails = [None]
    application.fail_list.delete(0, "end")
    application.fail_list.insert("end", "（这次没有产生 fail_*.txt）")
    application.fail_list.selection_set(0)
    opened.clear()
    application.open_selected_fail()
    check("失败用例：没有文件时点占位行不会报错、也不会打开东西", not opened)

    # ---- 5b. 预览窗本身（用真实的 open_preview） -------------------------- #
    del application.open_preview                 # 去掉上面的临时替身，走真实实现
    application.refresh_fail_list()

    def preview_windows():
        return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]

    application.fail_list.selection_clear(0, "end")
    application.fail_list.selection_set(0)
    application.open_selected_fail()
    pump(root, 0.3)

    windows = preview_windows()
    first_path = listed[0]
    check("预览窗：单击后弹出了一个 Toplevel 窗口", len(windows) == 1, str(len(windows)))
    check("预览窗：标题就是文件名", windows and windows[0].title() == first_path.name,
          repr(windows[0].title() if windows else ""))
    shown = application.preview_text.get("1.0", "end-1c")
    check("预览窗：内容和文件全文一致",
          shown == first_path.read_text(encoding="utf-8", errors="replace"),
          f"{len(shown)} 字符")
    check("预览窗：日志里追加了「已打开」确认",
          f"已打开 {first_path.name}" in application.log_text.get("1.0", "end"))
    check("预览窗：内容区是只读的（disabled）",
          str(application.preview_text["state"]) == "disabled")
    check("预览窗：Ctrl+C 已经绑了复制处理",
          bool(application.preview_text.bind("<Control-c>")))

    # 连点同一个文件：不能越开越多，也不该重复读
    win_before = windows[0]
    for _ in range(3):
        application.open_selected_fail()
    pump(root, 0.2)
    check("预览窗：连点同一个文件不会开出一堆窗口",
          len(preview_windows()) == 1 and application.preview_window is win_before,
          f"{len(preview_windows())} 个窗口")

    # 点另一个文件：内容要跟着换，窗口还是同一个
    if len(listed) >= 2:
        application.fail_list.selection_clear(0, "end")
        application.fail_list.selection_set(1)
        application.open_selected_fail()
        pump(root, 0.3)
        second_path = listed[1]
        check("预览窗：点另一个文件时内容和标题都换了",
              application.preview_text.get("1.0", "end-1c")
              == second_path.read_text(encoding="utf-8", errors="replace")
              and application.preview_window.title() == second_path.name,
              application.preview_window.title())
        check("预览窗：换文件时复用的是同一个窗口",
              application.preview_window is win_before and len(preview_windows()) == 1)

    # 复制：选中一段按 Ctrl+C 的处理器，以及「复制全部内容」
    body = application.preview_text.get("1.0", "end-1c")
    application.preview_text.tag_add("sel", "1.0", "1.4")
    application._copy_selection()
    root.update()
    check("预览窗：选中后复制的是选中的那一段",
          root.clipboard_get() == body[:4], repr(root.clipboard_get()[:20]))
    application.preview_text.tag_remove("sel", "1.0", "end")
    application._copy_all()
    root.update()
    check("预览窗：「复制全部内容」把全文放进了剪贴板",
          root.clipboard_get() == body, f"{len(root.clipboard_get())} 字符")
    check("预览窗：全文里有「复现命令」那一行，方便直接粘贴",
          "复现命令" in root.clipboard_get())

    # 读不到文件时：小窗里给人话，不甩系统报错原文
    ghost = OUT / "这个文件根本不存在_fail_9.txt"
    application.open_preview(ghost)
    pump(root, 0.3)
    ghost_text = application.preview_text.get("1.0", "end-1c")
    check("预览窗：读不到文件时给出人话提示、并带上完整路径",
          "读不到这个文件" in ghost_text and str(ghost) in ghost_text
          and "WinError" not in ghost_text and "Errno" not in ghost_text,
          ghost_text.splitlines()[0] if ghost_text else "")

    # 关掉小窗：主界面照常
    application._close_preview()
    pump(root, 0.3)
    check("预览窗：关掉之后窗口真的没了",
          not preview_windows() and application.preview_window is None)
    application.fail_list.selection_clear(0, "end")
    application.fail_list.selection_set(0)
    application.open_selected_fail()             # 关掉之后还能再点开
    pump(root, 0.3)
    check("预览窗：关掉以后还能重新点开",
          len(preview_windows()) == 1 and application.preview_window is not None,
          f"窗口数={len(preview_windows())} 选中={application.fail_list.curselection()}")
    application._close_preview()

    # 「定位到文件夹」这个备选能力要留着
    def boom(_p):
        raise OSError("[WinError 5] 拒绝访问")

    errs = []
    app_module.messagebox.showerror = lambda *a, **k: errs.append(a)
    original_reveal = app_module.reveal_in_folder
    app_module.reveal_in_folder = boom
    miss = ROOT / "_selftest" / "根本不存在_fail_1.txt"
    try:
        t0 = time.time()
        app_module.StressApp.reveal_path(application, miss)   # 后台线程
        immediate = time.time() - t0
        pump(root, 5, until=lambda: bool(errs))               # 等后台线程把错误抛回主线程
    finally:
        app_module.reveal_in_folder = original_reveal
    text = " ".join(str(x) for x in errs[-1]) if errs else ""
    check("定位到文件夹：reveal_path 立刻返回，不等后台线程", immediate < 0.2, f"{immediate:.3f}s")
    check("定位到文件夹：失败时的提示是人话、带完整路径、不甩系统报错原文",
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

    # ---- 7. 对拍（--ref）：界面填参考程序、统计条新格式、列表分三类 ---------- #
    ref_diff = WORK / "ref_diff.py"
    ref_diff.write_text(
        "import sys\nsys.stdin.read()\n"
        "print('sum = 0')\nprint('average = 0')\nprint('max/min = 0')\n",
        encoding="utf-8")
    ref_crash = WORK / "ref_crash.py"
    ref_crash.write_text("import sys\nsys.stdin.read()\nraise SystemExit(5)\n", encoding="utf-8")

    out_ref = OUT / "ref"
    if out_ref.exists():
        shutil.rmtree(out_ref)
    out_ref.mkdir(parents=True)
    application.target_var.set(str(target))
    application.ref_var.set(str(ref_diff))
    application.count_var.set("12")
    application.timeout_var.set("1")
    application.seed_var.set("123")
    application.outdir = out_ref
    application.outdir_var.set(str(out_ref))
    warnings.clear()
    application.start()
    pump(root, 90, until=lambda: application.running is False)
    pump(root, 0.8)

    banner = application.stats_label["text"]
    check("对拍：统计横条显示了新格式（带「不一致 k 组」）",
          "/ 不一致" in banner and re.search(r"不一致 \d+ 组", banner) is not None, repr(banner))
    check("对拍：真实拼进了 --ref 参数",
          "--ref" in application.log_text.get("1.0", "end"),
          repr(application.log_text.get("1.0", "end").splitlines()[8] if
               len(application.log_text.get("1.0", "end").splitlines()) > 8 else ""))
    kinds = [application.fail_list.get(i) for i in range(application.fail_list.size())]
    check("对拍：失败列表同时列出「崩溃」和「答案不一致」",
          any("[崩溃]" in k for k in kinds) and any("[答案不一致]" in k for k in kinds),
          str(kinds[:3]))
    diff_index = next((i for i, k in enumerate(kinds) if "[答案不一致]" in k), None)
    if diff_index is not None:
        application.fail_list.selection_clear(0, "end")
        application.fail_list.selection_set(diff_index)
        application.open_selected_fail()
        pump(root, 0.3)
    diff_name = application.preview_path.name if application.preview_path else ""
    check("对拍：点 diff_*.txt 也能在预览窗里看到内容",
          diff_name.startswith("diff_")
          and "第一处不同" in application.preview_text.get("1.0", "end-1c")
          and "复现命令" in application.preview_text.get("1.0", "end-1c"),
          diff_name)
    application._close_preview()

    # 参考程序自己崩了：统计条下面补一句，且绝不能写 fail_*/diff_*
    # 这里换一个「永远不崩」的被测试程序，才能干净地看出参考程序的错没算到它头上
    out_ref2 = OUT / "ref2"
    if out_ref2.exists():
        shutil.rmtree(out_ref2)
    out_ref2.mkdir(parents=True)
    application.target_var.set(str(ROOT / "templates" / "examples" / "gen_array_target.py"))
    application.ref_var.set(str(ref_crash))
    application.outdir = out_ref2
    application.outdir_var.set(str(out_ref2))
    application.start()
    pump(root, 90, until=lambda: application.running is False)
    pump(root, 0.8)
    banner2 = application.stats_label["text"]
    check("对拍：参考程序自己崩了，被测试程序一组都没被判错（崩/不一致都是 0）",
          "崩 0 组" in banner2 and "不一致 0 组" in banner2, repr(banner2))
    check("对拍：参考程序自己崩了会单独提示一句",
          "参考程序自身出错" in banner2, repr(banner2))
    check("对拍：这种情况不写 fail_*.txt / diff_*.txt，只写 ref_fail_*.txt",
          not list(out_ref2.glob("fail_*.txt")) and not list(out_ref2.glob("diff_*.txt"))
          and len(list(out_ref2.glob("ref_fail_*.txt"))) >= 1,
          str([p.name for p in out_ref2.iterdir()]))

    # ---- 9. 一键套用 templates/ 里的模板 ----------------------------------- #
    box = application.template_box
    values = list(box["values"])
    check("模板：下拉框是只读的（state=readonly）", str(box["state"]) == "readonly", str(box["state"]))
    check("模板：第一项固定是「（不使用模板）」",
          bool(values) and values[0] == "（不使用模板）", str(values[:2]))
    template_names = [v for v in values if v.endswith(".py")]
    check("模板：列出了 templates/ 下这一层的 6 个 gen_*.py（不含 examples/）",
          template_names == ["gen_array.py", "gen_graph.py", "gen_matrix.py",
                             "gen_multi.py", "gen_query.py", "gen_string.py"],
          str(template_names))
    check("模板：找到了 templates 目录并绑好了选择事件",
          application.templates_dir is not None and len(application.template_paths) == 6
          and bool(box.bind("<<ComboboxSelected>>")),
          str(application.templates_dir))

    disk_before_bytes = application.gen_py.read_bytes()
    disk_before = disk_before_bytes.decode("utf-8")
    application.load_gen()                      # 从磁盘重新载入，保证起点干净

    application.template_var.set("gen_array.py")
    application.on_template_selected()
    array_text = (ROOT / "templates" / "gen_array.py").read_text(encoding="utf-8")
    check("模板：选 gen_array.py 后编辑区变成它的内容",
          application.gen_text.get("1.0", "end-1c") == array_text,
          f"{len(array_text)} 字符")
    check("模板：套用后标成「还没保存」，但没写盘",
          application.gen_dirty is True and "还没保存" in application.gen_state_var.get()
          and application.gen_py.read_text(encoding="utf-8") == disk_before,
          application.gen_state_var.get())

    # 编辑区有未保存的改动时，再选另一个模板要先弹确认框
    asked = []
    real_ask = app_module.messagebox.askyesno
    app_module.messagebox.askyesno = lambda *a, **k: (asked.append(a), False)[1]
    application.template_var.set("gen_string.py")
    application.on_template_selected()
    check("模板：有未保存改动时会先弹确认框",
          len(asked) == 1 and "未保存" in str(asked[0]) and "覆盖" in str(asked[0]),
          str(asked[0]) if asked else "(没弹)")
    check("模板：点「否」时编辑区不动、下拉框退回「（不使用模板）」",
          application.gen_text.get("1.0", "end-1c") == array_text
          and application.template_var.get() == "（不使用模板）",
          application.template_var.get())

    asked.clear()
    app_module.messagebox.askyesno = lambda *a, **k: (asked.append(a), True)[1]
    application.template_var.set("gen_string.py")
    application.on_template_selected()
    app_module.messagebox.askyesno = real_ask
    string_text = (ROOT / "templates" / "gen_string.py").read_text(encoding="utf-8")
    check("模板：点「是」之后编辑区换成 gen_string.py 的内容",
          application.gen_text.get("1.0", "end-1c") == string_text and len(asked) == 1)

    # 保存之后要真的能跑
    out_tpl = OUT / "template"
    if out_tpl.exists():
        shutil.rmtree(out_tpl)
    out_tpl.mkdir(parents=True)
    check("模板：点「保存 gen.py」把模板写进磁盘",
          application.save_gen()
          and application.gen_py.read_text(encoding="utf-8") == string_text
          and application.gen_dirty is False)
    application.target_var.set(str(ROOT / "templates" / "examples" / "gen_string_target.py"))
    application.ref_var.set("")
    application.count_var.set("3")
    application.timeout_var.set("1")
    application.seed_var.set("123")
    application.outdir = out_tpl
    application.outdir_var.set(str(out_tpl))
    warnings.clear()
    application.start()
    pump(root, 90, until=lambda: application.running is False)
    pump(root, 0.5)
    check("模板：套用+保存之后能正常跑（字符串模板 + 对应示例目标）",
          application.stats_label["text"] == "通过 3 组 / 崩 0 组 / 超时 0 组",
          repr(application.stats_label["text"]))

    # 收尾：把 gen.py 还原成进来时的样子（按字节还原，免得顺手改了换行符；外面的 finally 还会再兜一道）
    application.gen_py.write_bytes(disk_before_bytes)
    application.load_gen()
    check("模板：自检收尾把 gen.py 按字节还原了",
          application.gen_py.read_bytes() == disk_before_bytes)

    # 找不到 templates 目录时：下拉框显示提示并禁用（用假的程序目录触发的真实分支）
    real_resolve = app_module.resolve_working_files
    fake_dir = HERE / "假装没有模板的目录"
    fake_dir.mkdir(parents=True, exist_ok=True)
    app_module.resolve_working_files = lambda: (fake_dir / "main.py", fake_dir / "gen.py", fake_dir)
    try:
        stranded = app_module.StressApp(root)      # 只读它的控件状态，不跑事件循环
    finally:
        app_module.resolve_working_files = real_resolve
    check("模板：找不到 templates 目录时，下拉框显示提示并被禁用",
          list(stranded.template_box["values"]) == [app_module.NO_TEMPLATES_DIR]
          and str(stranded.template_box["state"]) == "disabled"
          and stranded.template_var.get() == app_module.NO_TEMPLATES_DIR,
          f"{list(stranded.template_box['values'])} / state={stranded.template_box['state']}")

    # ---- 10. 关窗 ---------------------------------------------------------- #
    application.on_close()
    check("关窗：窗口正常销毁", True)

    failed = [n for n, ok in _results if not ok]
    print("\n" + "=" * 60)
    print(f"界面自检：{len(_results) - len(failed)} 项通过 / {len(failed)} 项失败")
    for name in failed:
        print("  FAILED: " + name)
    return 1 if failed else 0


def main():
    """跑自检，并且无论如何都把 gen.py 按字节还原（自检不该改交付物）。"""
    gen_py = ROOT / "gen.py"
    original = gen_py.read_bytes()
    try:
        return run_checks()
    finally:
        if gen_py.read_bytes() != original:
            gen_py.write_bytes(original)
            print("（自检改动了 gen.py，已按字节还原）", flush=True)


if __name__ == "__main__":
    sys.exit(main())
