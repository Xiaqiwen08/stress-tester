#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压力测试器图形界面外壳（app.py）

只用 Python 标准库里的 tkinter，不依赖任何第三方界面库。
放在 main.py 同一个目录里，用 `python app.py` 启动即可，或者打包成 exe 双击运行。

它只是一个"外壳"，干这些事：
    1. 用 subprocess 启动：python main.py <被测试程序> --count N --timeout T [--seed S]
    2. 后台线程实时读取 main.py 的 stdout，一行一行贴到界面日志区（界面不会卡死）
    3. main.py 结尾那行统计（通过 x 组 / 崩 n 组 / 超时 m 组）单独放大显示
    4. 列出这次产生的 fail_1.txt … fail_5.txt，点一下用系统默认程序打开
    5. 「停止」会把 main.py 连同它启动的被测试进程整棵进程树一起结束掉

main.py 保持原样，一行都不用改。
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

APP_TITLE = "Python 压力测试器（图形界面）"
POLL_MS = 60                 # 主线程多久去队列里取一次新日志
MAX_LOG_LINES = 4000         # 日志区最多留多少行，超出就从头删
DRAIN_WAIT_SECONDS = 2.0     # 进程结束后，最多再等这么久把剩余输出收干净
MATCH_FAIL_FILES = "fail_*.txt"

# main.py 结尾那行：通过 151 组 / 崩 47 组 / 超时 2 组
STATS_RE = re.compile(r"^通过\s+(\d+)\s+组\s*/\s*崩\s+(\d+)\s+组\s*/\s*超时\s+(\d+)\s+组\s*$")
# main.py 每组一行： [   4/200] 崩溃    0.064s  返回码=1  ZeroDivisionError: ...
PROGRESS_RE = re.compile(r"^\[\s*(\d+)\s*/\s*(\d+)\s*\]\s*(通过|崩溃|超时)")

MONO_FONT = ("Consolas", 10)
UI_FONT = ("Microsoft YaHei UI", 10)
BIG_FONT = ("Microsoft YaHei UI", 14, "bold")


# --------------------------------------------------------------------------- #
# 路径 / 解释器 / 输出目录
# --------------------------------------------------------------------------- #
def app_dir() -> Path:
    """app.py 所在目录；打包成 exe 之后就是 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_dir() -> Path | None:
    """PyInstaller 打包后解压出来的临时目录（没打包就是 None）。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return None


def resolve_working_files():
    """决定用哪一份 main.py / gen.py。

    优先用跟 app.py（或 exe）放在一起的那份，找不到就退回打包时塞进去的那份。
    gen.py 如果只存在于打包里，会尽量复制一份到 exe 旁边，方便用户直接改。
    """
    workdir = app_dir()
    bundled = bundled_dir()

    main_py = workdir / "main.py"
    if not main_py.is_file() and bundled is not None:
        candidate = bundled / "main.py"
        if candidate.is_file():
            main_py = candidate

    gen_py = workdir / "gen.py"
    if not gen_py.is_file() and bundled is not None:
        candidate = bundled / "gen.py"
        if candidate.is_file():
            try:
                shutil.copyfile(candidate, workdir / "gen.py")
                gen_py = workdir / "gen.py"
            except OSError:
                gen_py = candidate

    return main_py, gen_py, workdir


def resolve_outdir(workdir: Path) -> Path:
    """失败数据写哪里：优先写在程序旁边，写不进去就退到用户主目录。"""
    probe = workdir / ".__write_probe.tmp"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return workdir
    except OSError:
        pass
    fallback = Path.home() / "压力测试结果"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def find_python_interpreter() -> str:
    """用哪个解释器去跑 main.py。

    没打包时就是当前解释器；打包成 exe 之后 sys.executable 是 exe 自己，
    必须另找一个真正的 python.exe，否则 main.py 根本跑不起来。
    """
    if not getattr(sys, "frozen", False):
        return sys.executable

    candidates: list[str] = []
    for name in ("python.exe", "python3.exe", "py.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    for base, patterns in (
        (os.environ.get("LOCALAPPDATA"), ("Programs/Python/Python3*/python.exe",)),
        (os.environ.get("ProgramFiles"), ("Python3*/python.exe",)),
        ("C:\\", ("Python3*/python.exe",)),
    ):
        if not base:
            continue
        root = Path(base)
        for pattern in patterns:
            try:
                hits = sorted(root.glob(pattern), reverse=True)
            except OSError:
                hits = []
            candidates.extend(str(h) for h in hits)

    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[0] if unique else "python"


def enable_dpi_awareness() -> None:
    """高分屏上别糊。失败就算了，不影响使用。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def apply_scaling(root: tk.Tk) -> None:
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
    except Exception:
        pass


def open_with_system(path: Path) -> None:
    """用系统默认程序打开文件/目录。"""
    if os.name == "nt":
        os.startfile(str(path))          # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


# --------------------------------------------------------------------------- #
# 界面
# --------------------------------------------------------------------------- #
class StressApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue: "queue.Queue[tuple[str, object]]" = queue.Queue()

        self.proc: subprocess.Popen | None = None
        self.reader_thread: threading.Thread | None = None
        self.waiter_thread: threading.Thread | None = None
        self.running = False
        self.stop_requested = False
        self.run_started_at = 0.0
        self.log_line_count = 0
        self.current_fails: list[Path | None] = []
        self.stats_text = ""
        self.last_opened_path: Path | None = None   # 防重复打开，见 open_selected_fail
        self.last_opened_at = 0.0

        self.main_py, self.gen_py, self.workdir = resolve_working_files()
        self.outdir = resolve_outdir(self.workdir)

        self.target_var = tk.StringVar()
        self.python_var = tk.StringVar(value=find_python_interpreter())
        self.count_var = tk.StringVar(value="200")
        self.timeout_var = tk.StringVar(value="1.0")
        self.seed_var = tk.StringVar()
        self.outdir_var = tk.StringVar(value=str(self.outdir))
        self.gen_state_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="空闲")
        self.gen_dirty = False

        self._build_ui()
        self.load_gen()
        self.refresh_fail_list()
        self._print_environment()
        self.check_environment()
        self.root.after(POLL_MS, self._poll_queue)

    # ------------------------------------------------------------------ #
    # 搭界面
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.geometry("1040x800")
        self.root.minsize(860, 640)

        try:
            style = ttk.Style()
            if "vista" in style.theme_names():
                style.theme_use("vista")
            style.configure(".", font=UI_FONT)
        except tk.TclError:
            pass

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)      # 中间那块（gen.py + 日志）负责伸缩

        self._build_settings(outer, row=0)
        self._build_controls(outer, row=1)
        self._build_stats(outer, row=2)
        self._build_main_area(outer, row=3)
        self._build_fail_list(outer, row=4)

    def _build_settings(self, parent: ttk.Frame, row: int) -> None:
        box = ttk.LabelFrame(parent, text=" 被测试程序与参数 ", padding=10)
        box.grid(row=row, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)

        # 被测试程序
        ttk.Label(box, text="被测试程序：").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.target_var).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(box, text="选择被测试程序…", command=self.choose_target).grid(row=0, column=2)

        # 解释器
        ttk.Label(box, text="Python 解释器：").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(box, textvariable=self.python_var).grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(6, 0))
        ttk.Button(box, text="浏览…", command=self.choose_python).grid(row=1, column=2, pady=(6, 0))
        ttk.Label(box, text="（用它启动 main.py）", foreground="#666666").grid(
            row=2, column=1, sticky="w", pady=(0, 4))

        # 三个参数
        params = ttk.Frame(box)
        params.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(params, text="测试组数：").grid(row=0, column=0, sticky="w")
        ttk.Entry(params, textvariable=self.count_var, width=8).grid(row=0, column=1, padx=(0, 16))
        ttk.Label(params, text="超时秒数：").grid(row=0, column=2, sticky="w")
        ttk.Entry(params, textvariable=self.timeout_var, width=8).grid(row=0, column=3, padx=(0, 16))
        ttk.Label(params, text="随机种子：").grid(row=0, column=4, sticky="w")
        ttk.Entry(params, textvariable=self.seed_var, width=14).grid(row=0, column=5, padx=(0, 10))
        ttk.Label(params, text="留空＝每次随机（跑完会打印种子，照着填就能复现）",
                  foreground="#666666").grid(row=0, column=6, sticky="w")

        # 输出目录
        out = ttk.Frame(box)
        out.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="失败数据目录：").grid(row=0, column=0, sticky="w")
        ttk.Label(out, textvariable=self.outdir_var, foreground="#333333").grid(row=0, column=1, sticky="w")
        ttk.Button(out, text="打开目录", command=lambda: self.open_path(self.outdir)).grid(row=0, column=2)

    def _build_controls(self, parent: ttk.Frame, row: int) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=row, column=0, sticky="ew", pady=(8, 4))
        bar.columnconfigure(3, weight=1)

        self.start_btn = ttk.Button(bar, text="开始", command=self.start)
        self.start_btn.grid(row=0, column=0)
        self.stop_btn = ttk.Button(bar, text="停止", command=self.stop, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=(8, 0))
        ttk.Button(bar, text="清空日志", command=self.clear_log).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(bar, textvariable=self.status_var, foreground="#00429d").grid(
            row=0, column=3, sticky="e")

    def _build_stats(self, parent: ttk.Frame, row: int) -> None:
        self.stats_label = tk.Label(
            parent, text="还没开始跑", font=BIG_FONT,
            bg="#eeeeee", fg="#555555", padx=12, pady=8, anchor="center",
        )
        self.stats_label.grid(row=row, column=0, sticky="ew", pady=(2, 8))

    def _build_main_area(self, parent: ttk.Frame, row: int) -> None:
        paned = ttk.PanedWindow(parent, orient="horizontal")
        paned.grid(row=row, column=0, sticky="nsew")

        # 左：gen.py 编辑器
        left = ttk.LabelFrame(paned, text=" gen.py（数据生成规则，可以直接在这里改） ", padding=8)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(left)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        toolbar.columnconfigure(1, weight=1)
        ttk.Button(toolbar, text="保存 gen.py", command=self.save_gen).grid(row=0, column=0)
        ttk.Button(toolbar, text="重新载入", command=self.load_gen).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(toolbar, textvariable=self.gen_state_var, foreground="#666666").grid(
            row=0, column=2, sticky="e")

        text_wrap = ttk.Frame(left)
        text_wrap.grid(row=1, column=0, sticky="nsew")
        text_wrap.columnconfigure(0, weight=1)
        text_wrap.rowconfigure(0, weight=1)
        self.gen_text = tk.Text(text_wrap, wrap="none", undo=True, font=MONO_FONT, height=14)
        self.gen_text.grid(row=0, column=0, sticky="nsew")
        gen_scroll = ttk.Scrollbar(text_wrap, orient="vertical", command=self.gen_text.yview)
        gen_scroll.grid(row=0, column=1, sticky="ns")
        gen_xscroll = ttk.Scrollbar(text_wrap, orient="horizontal", command=self.gen_text.xview)
        gen_xscroll.grid(row=1, column=0, sticky="ew")
        self.gen_text.configure(yscrollcommand=gen_scroll.set, xscrollcommand=gen_xscroll.set)
        self.gen_text.bind("<<Modified>>", self._on_gen_modified)

        # 右：实时日志
        right = ttk.LabelFrame(paned, text=" 实时日志 ", padding=8)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(right, wrap="none", font=MONO_FONT, height=20,
                                     state="disabled", background="#fbfbfb")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        self.log_text.tag_config("pass", foreground="#0a7d28")
        self.log_text.tag_config("crash", foreground="#c00000")
        self.log_text.tag_config("timeout", foreground="#b06000")
        self.log_text.tag_config("stat", foreground="#00429d", font=("Consolas", 10, "bold"))
        self.log_text.tag_config("error", foreground="#c00000", font=("Consolas", 10, "bold"))
        self.log_text.tag_config("dim", foreground="#777777")

        paned.add(left, weight=3)
        paned.add(right, weight=4)

    def _build_fail_list(self, parent: ttk.Frame, row: int) -> None:
        box = ttk.LabelFrame(parent, text=" 失败用例（点一下用系统默认程序打开） ", padding=8)
        box.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        box.columnconfigure(0, weight=1)

        list_wrap = ttk.Frame(box)
        list_wrap.grid(row=0, column=0, sticky="ew")
        list_wrap.columnconfigure(0, weight=1)
        self.fail_list = tk.Listbox(list_wrap, height=5, activestyle="none",
                                    font=("Microsoft YaHei UI", 9))
        self.fail_list.grid(row=0, column=0, sticky="ew")
        fail_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.fail_list.yview)
        fail_scroll.grid(row=0, column=1, sticky="ns")
        self.fail_list.configure(yscrollcommand=fail_scroll.set)

        # 只绑单击打开。不再绑 <Double-Button-1>：双击本来就会先触发一次单击，
        # 两处都绑等于同一个文件被打开两遍。
        self.fail_list.bind("<ButtonRelease-1>", self.open_selected_fail)
        self.fail_list.bind("<Return>", self.open_selected_fail)

    # ------------------------------------------------------------------ #
    # 日志
    # ------------------------------------------------------------------ #
    def append_log(self, line: str, tag: str | None = None) -> None:
        if tag is None:
            tag = self._tag_for(line)
        self.log_text.configure(state="normal")
        if tag:
            self.log_text.insert("end", line + "\n", tag)
        else:
            self.log_text.insert("end", line + "\n")
        self.log_line_count += 1
        if self.log_line_count > MAX_LOG_LINES:
            drop = MAX_LOG_LINES // 5
            self.log_text.delete("1.0", f"{drop + 1}.0")
            self.log_line_count -= drop
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    @staticmethod
    def _tag_for(line: str) -> str | None:
        if PROGRESS_RE.match(line):
            status = PROGRESS_RE.match(line).group(3)          # type: ignore[union-attr]
            return {"通过": "pass", "崩溃": "crash", "超时": "timeout"}.get(status)
        if STATS_RE.match(line):
            return "stat"
        if line.startswith("错误：") or line.startswith("警告："):
            return "error"
        if "-> 已保存" in line:
            return "dim"
        return None

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log_line_count = 0

    def _print_environment(self) -> None:
        self.append_log("=" * 76, "dim")
        self.append_log(f"main.py  ：{self.main_py}", "dim")
        self.append_log(f"gen.py   ：{self.gen_py}", "dim")
        self.append_log(f"解释器   ：{self.python_var.get()}", "dim")
        self.append_log(f"输出目录 ：{self.outdir}", "dim")
        self.append_log("=" * 76, "dim")

    # ------------------------------------------------------------------ #
    # gen.py
    # ------------------------------------------------------------------ #
    def load_gen(self) -> None:
        try:
            content = self.gen_py.read_text(encoding="utf-8")
        except OSError as exc:
            content = ""
            self.gen_state_var.set(f"读不到 gen.py：{exc}")
        self.gen_text.configure(state="normal")
        self.gen_text.delete("1.0", "end")
        self.gen_text.insert("1.0", content)
        self.gen_text.edit_modified(False)
        self.gen_dirty = False
        self.gen_state_var.set("已载入" if content else "gen.py 是空的或不存在")

    def _on_gen_modified(self, _event=None) -> None:
        if not self.gen_text.edit_modified():
            return
        self.gen_text.edit_modified(False)
        self.gen_dirty = True
        self.gen_state_var.set("有改动，还没保存")

    def save_gen(self) -> bool:
        content = self.gen_text.get("1.0", "end-1c")
        try:
            self.gen_py.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("保存失败", f"写不进 {self.gen_py}\n\n{exc}")
            return False
        self.gen_dirty = False
        self.gen_state_var.set(f"已保存 {time.strftime('%H:%M:%S')}")
        if self.log_line_count:
            self.append_log(f"（已保存 gen.py：{self.gen_py}）", "dim")
        return True

    # ------------------------------------------------------------------ #
    # 路径选择
    # ------------------------------------------------------------------ #
    def choose_target(self) -> None:
        initial = Path(self.target_var.get()).parent if self.target_var.get() else self.workdir
        path = filedialog.askopenfilename(
            title="选择被测试的 Python 程序",
            initialdir=str(initial),
            filetypes=[("Python 文件", "*.py"), ("所有文件", "*.*")],
        )
        if path:
            self.target_var.set(path)

    def choose_python(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Python 解释器",
            initialdir=str(Path(self.python_var.get()).parent) if self.python_var.get() else str(self.workdir),
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if path:
            self.python_var.set(path)

    def open_path(self, path: Path) -> None:
        try:
            open_with_system(path)
        except Exception:
            # 不把 "[WinError 5] 拒绝访问" 这种原文甩给用户，换成能照着做的提示
            messagebox.showerror(
                "打不开这个文件",
                "打不开这个文件，可能是被安全软件拦截了，请手动用记事本打开。\n\n"
                "文件位置：\n{}".format(path),
            )

    # ------------------------------------------------------------------ #
    # 失败用例列表
    # ------------------------------------------------------------------ #
    def refresh_fail_list(self) -> None:
        self.fail_list.delete(0, "end")
        self.current_fails = []

        entries: list[Path] = []
        for index in range(1, 6):
            path = self.outdir / f"fail_{index}.txt"
            if not path.is_file():
                continue
            # 只列这次运行产生的（run_started_at 为 0 时表示还没跑过，列出已有的）
            if self.run_started_at and path.stat().st_mtime < self.run_started_at - 5:
                continue
            entries.append(path)

        if not entries:
            self.fail_list.insert("end", "（这次没有产生 fail_*.txt）")
            self.fail_list.itemconfigure(0, foreground="#888888")
            self.current_fails = [None]
            return

        self.current_fails = list(entries)   # 列表里的第 i 行对应哪个文件

        for path in entries:
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            stamp = time.strftime("%H:%M:%S", time.localtime(path.stat().st_mtime))
            self.fail_list.insert("end", f"{path.name}    {size} 字节    {stamp}    {path}")

    def open_selected_fail(self, _event=None) -> str | None:
        selection = self.fail_list.curselection()
        if not selection:
            return None
        index = selection[0]
        if index >= len(self.current_fails):
            return None
        path = self.current_fails[index]
        if path is None:
            return None

        # 双击会被系统当成「两次单击」，只靠去掉双绑还不够，这里再兜一道：
        # 同一个文件 1.5 秒内只打开一次，绝不会重复弹两个窗口。
        now = time.time()
        if path == self.last_opened_path and now - self.last_opened_at < 1.5:
            return "break"
        self.last_opened_path = path
        self.last_opened_at = now

        self.open_path(path)
        return "break"

    # ------------------------------------------------------------------ #
    # 开始 / 停止
    # ------------------------------------------------------------------ #
    def check_environment(self) -> None:
        if not self.main_py.is_file():
            self.append_log(f"错误：找不到 main.py（应该在 {self.workdir} 里）", "error")
            self.append_log("请把 app.py 和 main.py 放在同一个目录，再重新启动本程序。", "error")
        if not self.gen_py.is_file():
            self.append_log(f"提示：还没有 gen.py（{self.gen_py}），"
                            "可以在左边写一份再点「保存 gen.py」。", "error")

    def _read_form(self):
        """检查界面上的输入，返回 (target, python, count, timeout, seed) 或 None。"""
        target = self.target_var.get().strip().strip('"')
        if not target:
            messagebox.showwarning("还没有选程序", "请先点「选择被测试程序…」挑一个 .py 文件。")
            return None
        target_path = Path(target)
        if not target_path.is_file():
            messagebox.showerror("找不到文件", f"没有这个文件：\n{target_path}")
            return None
        if target_path.suffix.lower() != ".py":
            messagebox.showwarning("文件类型不对", "被测试程序必须是一个 .py 文件。")
            return None

        python_exe = self.python_var.get().strip().strip('"')
        if not python_exe:
            messagebox.showwarning("缺少解释器", "请填一个 Python 解释器的路径。")
            return None

        if not self.main_py.is_file():
            messagebox.showerror("找不到 main.py",
                                 f"main.py 应该在 {self.workdir} 里。\n"
                                 "请把 app.py 和 main.py 放在同一个目录。")
            return None

        try:
            count = int(self.count_var.get().strip())
            if count < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("测试组数不对", "测试组数要填一个大于 0 的整数，例如 200。")
            return None

        try:
            timeout = float(self.timeout_var.get().strip())
            if timeout <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("超时秒数不对", "超时秒数要填一个大于 0 的数，例如 1 或 1.5。")
            return None

        seed_text = self.seed_var.get().strip()
        seed = None
        if seed_text:
            try:
                seed = int(seed_text)
            except ValueError:
                messagebox.showwarning("随机种子不对", "随机种子要么留空，要么填一个整数，例如 123。")
                return None

        return target_path, python_exe, count, timeout, seed

    def start(self) -> None:
        if self.running:
            return
        form = self._read_form()
        if form is None:
            return
        target_path, python_exe, count, timeout, seed = form

        # 左边编辑器里有改动就先存盘，保证跑的是界面上看到的那份规则
        if self.gen_dirty or not self.gen_py.is_file():
            if not self.save_gen():
                return

        cmd = [
            python_exe, str(self.main_py), str(target_path),
            "--count", str(count),
            "--timeout", str(timeout),
            "--gen", str(self.gen_py),
            "--outdir", str(self.outdir),
        ]
        if seed is not None:
            cmd += ["--seed", str(seed)]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"   # 中文输出统一按 utf-8 读，避免乱码
        env["PYTHONUNBUFFERED"] = "1"

        creationflags = 0
        popen_kwargs = {}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
                            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True   # 方便整组一起杀

        self.clear_log()
        self.fail_list.delete(0, "end")
        self.current_fails = []
        self.append_log("执行命令：" + " ".join(f'"{c}"' if " " in c else c for c in cmd), "dim")
        self.append_log("", None)

        try:
            self.proc = subprocess.Popen(
                cmd, cwd=str(self.workdir), env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=creationflags, **popen_kwargs,
            )
        except OSError as exc:
            self.append_log(f"错误：启动不了 main.py：{exc}", "error")
            messagebox.showerror("启动失败", f"启动不了 main.py：\n{exc}")
            return

        self.running = True
        self.stop_requested = False
        self.run_started_at = time.time()
        self.stats_text = ""
        self.set_stats("正在跑…", "#fff4e0", "#8a5a00")
        self.status_var.set(f"正在运行（共 {count} 组）")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.reader_thread = threading.Thread(target=self._read_output, args=(self.proc,), daemon=True)
        self.reader_thread.start()
        self.waiter_thread = threading.Thread(target=self._wait_process, args=(self.proc,), daemon=True)
        self.waiter_thread.start()

    def stop(self) -> None:
        if not self.running or self.proc is None:
            return
        self.stop_requested = True
        self.stop_btn.configure(state="disabled")
        self.status_var.set("正在停止…")
        self.append_log("—— 正在停止：结束 main.py 及其启动的所有子进程 ——", "error")
        # 杀进程要调 taskkill（最多等 10 秒），放到后台线程去做，
        # 主线程立刻返回，界面在这期间照样能刷新、能点。
        proc = self.proc
        threading.Thread(target=self.kill_tree, args=(proc,), daemon=True).start()

    @staticmethod
    def kill_tree(proc: subprocess.Popen) -> None:
        """把 main.py 连同它启动的被测试进程整棵树结束掉。"""
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, check=False,
                )
            except Exception:
                pass
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        try:
            proc.kill()          # 兜底：直接结束我们自己启动的那个进程
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 后台线程
    # ------------------------------------------------------------------ #
    def _read_output(self, proc: subprocess.Popen) -> None:
        try:
            if proc.stdout is not None:
                for raw in proc.stdout:
                    self.queue.put(("line", raw.rstrip("\r\n")))
        except Exception as exc:
            self.queue.put(("line", f"（读取 main.py 输出时出错：{exc}）"))
        finally:
            try:
                if proc.stdout is not None:
                    proc.stdout.close()
            except Exception:
                pass

    def _wait_process(self, proc: subprocess.Popen) -> None:
        code = proc.wait()
        # 给读取线程一点时间把最后几行吐完（正常情况瞬间就好）
        if self.reader_thread is not None:
            self.reader_thread.join(timeout=DRAIN_WAIT_SECONDS)
        self.queue.put(("exit", code))

    # ------------------------------------------------------------------ #
    # 主线程：把队列里的东西贴到界面上
    # ------------------------------------------------------------------ #
    def _poll_queue(self) -> None:
        handled = 0
        try:
            while handled < 300:
                kind, payload = self.queue.get_nowait()
                handled += 1
                if kind == "line":
                    self._handle_line(str(payload))
                elif kind == "exit":
                    self._handle_exit(payload)          # type: ignore[arg-type]
        except queue.Empty:
            pass
        finally:
            self.root.after(POLL_MS, self._poll_queue)

    def _handle_line(self, line: str) -> None:
        self.append_log(line)
        match = STATS_RE.match(line)
        if match:
            passed, crashed, timed_out = (int(x) for x in match.groups())
            self.stats_text = line
            if crashed == 0 and timed_out == 0:
                self.set_stats(line, "#e6f7e6", "#0a7d28")
            elif crashed > 0:
                self.set_stats(line, "#fdecec", "#b00000")
            else:
                self.set_stats(line, "#fff4e0", "#8a5a00")
            return
        progress = PROGRESS_RE.match(line)
        if progress:
            self.status_var.set(f"正在运行：第 {progress.group(1)} / {progress.group(2)} 组")

    def _handle_exit(self, code) -> None:
        self.running = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.proc = None

        if self.stop_requested:
            self.status_var.set("已停止")
            if not self.stats_text:
                self.set_stats("已停止（没跑完）", "#eeeeee", "#555555")
        elif code == 0:
            self.status_var.set("完成：全部通过")
        elif code == 1:
            self.status_var.set("完成：发现了问题，看下面的失败用例")
        elif code == 2:
            self.status_var.set("出错了：用法或环境问题（看日志里的「错误：」）")
        else:
            self.status_var.set(f"结束（返回码 {code}）")

        self.append_log("", None)
        self.append_log(f"（main.py 已退出，返回码 {code}）", "dim")
        self.refresh_fail_list()

    def set_stats(self, text: str, background: str, foreground: str) -> None:
        self.stats_label.configure(text=text, bg=background, fg=foreground)

    # ------------------------------------------------------------------ #
    def on_close(self) -> None:
        if self.running and self.proc is not None:
            if not messagebox.askyesno("还在跑", "测试还没跑完，确定要退出吗？\n"
                                                  "（会把正在跑的被测试进程一起结束）"):
                return
            self.kill_tree(self.proc)
        self.root.destroy()


# --------------------------------------------------------------------------- #
def main() -> int:
    enable_dpi_awareness()
    root = tk.Tk()
    apply_scaling(root)
    app = StressApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
