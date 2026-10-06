# -*- coding: utf-8 -*-
"""templates/ 的自检：每个模板都要做到

  1. 可复现：同一个 --seed 生成的数据逐字节一致，换种子就不一样；
  2. 输入自洽：声明 n 个就真给 n 个，图不越界/不重边/不自环、询问不越界；
  3. 雷齐全：空、单个、最大规模、0、负数都真的出现过；
  4. 正文干净：只用 rnd / 已播种的 random，不碰 os.urandom、time.time、random.Random()；
  5. 配套示例目标程序能把这 200 组全部吃掉，退出码 0。

用法：
    python _selftest/template_check.py
"""

import importlib.util
import re
import random
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMPLATES = ROOT / "templates"
EXAMPLES = TEMPLATES / "examples"
WORK = HERE / "tpl_work"
PY = sys.executable

SAMPLES = 200
SEED = 123
OTHER_SEED = 999

NAMES = ["gen_array", "gen_string", "gen_multi", "gen_matrix", "gen_graph", "gen_query"]

SCALE_CONSTANT = {
    "gen_array": "N_MAX",
    "gen_string": "LEN_MAX",
    "gen_multi": "T_MAX",
    "gen_matrix": "N_MAX",
    "gen_graph": "N_MAX",
    "gen_query": "N_MAX",
}

HEADER_KEYWORDS = {
    "gen_array": ["空输入", "负数", "单个元素", "最大规模"],
    "gen_string": ["空串", "'-'", "最大长度"],
    "gen_multi": ["空输入", "负数", "最大规模", "k = 0"],
    "gen_matrix": ["空输入", "负数", "最大规模", "0 0"],
    "gen_graph": ["空输入", "负数", "最大规模", "自环"],
    "gen_query": ["空输入", "负数", "最大规模", "l == r"],
}

COMMON_KEYWORDS = ["适用题型", "生成的输入格式", "要改哪几行", "改这里", "不要删", "数据规模"]

FORBIDDEN_IN_TEMPLATES = ["os.urandom", "time.time", "random.Random(", "import os",
                          "import time", "import uuid", "import secrets"]

_results = []


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("   -> " + detail) if detail else ""), flush=True)
    return bool(ok)


def load_template(name, seed):
    """完全照 main.py 的做法加载模板：先给全局 random 播种，再注入 SEED / rnd。"""
    path = TEMPLATES / f"{name}.py"
    random.seed(seed)
    spec = importlib.util.spec_from_file_location("tpl_" + name, str(path))
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    module.SEED = seed
    module.rnd = random.Random(seed)
    return module


def sample(module, count):
    return [module.gen() for _ in range(count)]


# --------------------------------------------------------------------------- #
# 每种模板各自的自洽性检查：声明了几个数，就必须真给几个
# --------------------------------------------------------------------------- #
def validate(name, mod, data):
    facts = {"empty": data.strip() == ""}
    if facts["empty"]:
        return facts

    tok = data.split()

    if name == "gen_array":
        n = int(tok[0])
        vals = [int(x) for x in tok[1:]]
        assert len(vals) == n, "声明 {} 个数，实际给了 {} 个".format(n, len(vals))
        facts.update(single=n == 1, max=n == mod.N_MAX,
                     zero=any(v == 0 for v in vals), negative=any(v < 0 for v in vals))

    elif name == "gen_string":
        line = data.split("\n")[0]
        assert "\n" not in line
        facts.update(single=len(line) == 1, max=len(line) >= mod.LEN_MAX,
                     zero="0" in line, negative="-" in line,
                     blank=line.strip() == "" and line != "")

    elif name == "gen_multi":
        pos, groups, sizes, all_vals = 0, 0, [], []
        while pos < len(tok):
            k = int(tok[pos]); pos += 1
            vals = [int(x) for x in tok[pos:pos + k]]
            assert len(vals) == k, "某一组声明 {} 个数，实际给了 {} 个".format(k, len(vals))
            pos += k
            groups += 1
            sizes.append(k)
            all_vals.extend(vals)
        assert pos == len(tok)
        facts.update(groups=groups, single=(groups == 1 and sizes == [1]),
                     max=(groups == mod.T_MAX and max(sizes) == mod.N_MAX),
                     zero_group=(0 in sizes),
                     zero=any(v == 0 for v in all_vals), negative=any(v < 0 for v in all_vals))

    elif name == "gen_matrix":
        n, m = int(tok[0]), int(tok[1])
        vals = [int(x) for x in tok[2:]]
        assert len(vals) == n * m, "声明 {}x{}，实际给了 {} 个数".format(n, m, len(vals))
        facts.update(single=(n == 1 and m == 1), max=(n == mod.N_MAX and m == mod.M_MAX),
                     zero_matrix=(n == 0 and m == 0), one_row=(n == 1 and m > 1),
                     one_col=(m == 1 and n > 1),
                     zero=any(v == 0 for v in vals), negative=any(v < 0 for v in vals))

    elif name == "gen_graph":
        n, m = int(tok[0]), int(tok[1])
        width = 3 if mod.HAS_WEIGHT else 2
        rest = [int(x) for x in tok[2:]]
        assert len(rest) == m * width, "声明 {} 条边，实际给了 {} 个数".format(m, len(rest))
        edges = [tuple(rest[i:i + width]) for i in range(0, len(rest), width)]
        lo, hi = mod.BASE, mod.BASE + n - 1
        seen = set()
        for e in edges:
            u, v = e[0], e[1]
            assert lo <= u <= hi and lo <= v <= hi, "点编号越界: {}".format(e)
            if not mod.ALLOW_SELF_LOOP:
                assert u != v, "出现了自环: {}".format(e)
            if not mod.ALLOW_DUPLICATE:
                key = (min(u, v), max(u, v))
                assert key not in seen, "出现了重边: {}".format(e)
                seen.add(key)
        weights = [e[2] for e in edges] if mod.HAS_WEIGHT else []
        facts.update(single=(n == 1 and m == 0), max=(n == mod.N_MAX and m == mod.M_MAX),
                     zero_edges=(m == 0), base=mod.BASE,
                     zero=any(w == 0 for w in weights), negative=any(w < 0 for w in weights))

    elif name == "gen_query":
        n = int(tok[0])
        arr = [int(x) for x in tok[1:1 + n]]
        assert len(arr) == n, "声明 {} 个数，实际给了 {} 个".format(n, len(arr))
        pos = 1 + n
        q = int(tok[pos]); pos += 1
        pairs = []
        for _ in range(q):
            l, r = int(tok[pos]), int(tok[pos + 1]); pos += 2
            assert 1 <= l <= n and 1 <= r <= n, "询问越界: ({}, {})".format(l, r)
            if not mod.ALLOW_REVERSED_QUERY:
                assert l <= r, "出现 l > r 的非法区间: ({}, {})".format(l, r)
            pairs.append((l, r))
        assert pos == len(tok), "多出来 {} 个数没被解释".format(len(tok) - pos)
        facts.update(single=(n == 1 and q == 1), max=(n == mod.N_MAX and q == mod.Q_MAX),
                     same_lr=any(l == r for l, r in pairs),
                     full_range=any(l == 1 and r == n for l, r in pairs),
                     zero=any(v == 0 for v in arr), negative=any(v < 0 for v in arr))
    else:
        raise AssertionError("未知模板 " + name)

    return facts


def code_line_count(path):
    """示例目标程序的代码行数（不算空行、注释、模块文档字符串）。"""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'^""".*?"""', "", text, flags=re.S | re.M)
    return len([ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")])


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=str(ROOT), **kwargs)


def last_line(text):
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


# --------------------------------------------------------------------------- #
def main():
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)

    for name in NAMES:
        print("-" * 70)
        print(f"【{name}】", flush=True)
        template = TEMPLATES / f"{name}.py"
        target = EXAMPLES / f"{name}_target.py"
        source = template.read_text(encoding="utf-8")

        if not check(f"{name}：模板文件和配套示例都在", template.is_file() and target.is_file()):
            continue

        # ---- 头部四件事 + 规模常量 -------------------------------------- #
        missing = [k for k in COMMON_KEYWORDS if k not in source]
        check(f"{name}：头部写了「适用题型/输入格式/要改哪几行/边界数据/数据规模」", not missing,
              f"缺少 {missing}" if missing else "")
        missing = [k for k in HEADER_KEYWORDS[name] if k not in source]
        check(f"{name}：头部点明了该有的雷", not missing, f"缺少 {missing}" if missing else "")
        const = SCALE_CONSTANT[name]
        check(f"{name}：有规模常量 {const} 且带「改这里」注释",
              re.search(rf"^{const}\s*=", source, re.M) is not None and "改这里" in source)
        check(f"{name}：注释里标了「不要删」", "不要删" in source)

        # ---- 正文不许用的随机源 ------------------------------------------ #
        bad = [w for w in FORBIDDEN_IN_TEMPLATES if w in source]
        check(f"{name}：没有用 os.urandom / time.time / random.Random() 这些", not bad,
              f"发现 {bad}" if bad else "")
        imports = set(re.findall(r"^(?:import|from)\s+([A-Za-z_][\w.]*)", source, re.M))
        check(f"{name}：只 import 标准库里的 random", imports <= {"random"}, str(sorted(imports)))

        # ---- 生成 200 组并逐组校验 --------------------------------------- #
        mod = load_template(name, SEED)
        assert callable(mod.gen), "没有 gen()"
        data_list = sample(mod, SAMPLES)
        check(f"{name}：gen() 每次都返回 str", all(isinstance(d, str) for d in data_list))
        check(f"{name}：非空的组都以换行结尾（main.py 也这么建议）",
              all(d.endswith("\n") for d in data_list if d))

        bad_group = None
        facts_list = []
        for i, data in enumerate(data_list, 1):
            try:
                facts_list.append(validate(name, mod, data))
            except AssertionError as exc:
                bad_group = (i, str(exc), data[:120])
                break
        check(f"{name}：{SAMPLES} 组数据全都自洽（声明的个数和实际一致、编号不越界）",
              bad_group is None, str(bad_group) if bad_group else "")
        if bad_group:
            continue

        counters = {}
        for facts in facts_list:
            for key, value in facts.items():
                if isinstance(value, bool) and value:
                    counters[key] = counters.get(key, 0) + 1
        empty = sum(1 for f in facts_list if f.get("empty"))
        detail = "空 {} | 单个 {} | 最大规模 {} | 含0 {} | 含负数 {}".format(
            empty, counters.get("single", 0), counters.get("max", 0),
            counters.get("zero", 0), counters.get("negative", 0))
        check(f"{name}：空 / 单个 / 最大规模 / 0 / 负数 都真的出现过",
              empty > 0 and counters.get("single") and counters.get("max")
              and counters.get("zero") and counters.get("negative"), detail)
        extras = {k: v for k, v in counters.items()
                  if k in ("zero_group", "zero_matrix", "one_row", "one_col",
                           "zero_edges", "same_lr", "full_range", "blank")}
        check(f"{name}：专属的雷也出现过", all(v > 0 for v in extras.values()) if extras else True,
              str(extras))

        # 专项回归：n == 1 时也必须是 [0]（曾经漏过，n=1 既没 0 也没负数）
        if name == "gen_array":
            ones = [int(d.split()[1]) for d in data_list
                    if len(d.split()) >= 2 and int(d.split()[0]) == 1]
            check("gen_array：n=1 的那几组，值也一定是 0",
                  bool(ones) and all(v == 0 for v in ones),
                  f"n=1 出现 {len(ones)} 次，值集合 {sorted(set(ones))}")

        # ---- 可复现 ------------------------------------------------------ #
        again = sample(load_template(name, SEED), SAMPLES)
        check(f"{name}：同一个种子生成的数据逐字节一致", again == data_list)
        other = sample(load_template(name, OTHER_SEED), 30)
        check(f"{name}：换个种子数据就不一样了", other != data_list[:30])

        # ---- 示例目标程序能吃下全部 200 组 -------------------------------- #
        outdir = WORK / ("out_" + name)
        proc = run([PY, str(ROOT / "main.py"), str(target), "--gen", str(template),
                    "--count", str(SAMPLES), "--seed", str(SEED), "--quiet",
                    "--outdir", str(outdir)])
        want = f"通过 {SAMPLES} 组 / 崩 0 组 / 超时 0 组"
        check(f"{name}：配套示例吃掉全部 {SAMPLES} 组（不崩不超时）",
              proc.returncode == 0 and last_line(proc.stdout) == want,
              f"exit={proc.returncode} {last_line(proc.stdout)!r}")

        # ---- 示例目标程序单独喂空输入 ------------------------------------- #
        empty_run = run([PY, str(target)], input="")
        check(f"{name}：示例目标程序喂空输入也返回 0", empty_run.returncode == 0,
              f"exit={empty_run.returncode}")

        # ---- 示例目标程序够短 --------------------------------------------- #
        lines = code_line_count(target)
        check(f"{name}：示例目标程序很短（5~15 行代码）", 5 <= lines <= 15, f"{lines} 行")

        # ---- 模板能单独运行预览 ------------------------------------------- #
        preview = run([PY, str(template)])
        check(f"{name}：模板能单独运行预览（python {template.name}）",
              preview.returncode == 0 and "--- 第 1 组 ---" in preview.stdout,
              f"exit={preview.returncode}")

    failed = [n for n, ok in _results if not ok]
    print("\n" + "=" * 70)
    print(f"模板自检：{len(_results) - len(failed)} 项通过 / {len(failed)} 项失败")
    for name in failed:
        print("  FAILED: " + name)

    shutil.rmtree(WORK, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
