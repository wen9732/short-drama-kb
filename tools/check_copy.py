#!/usr/bin/env python3
"""照抄检查：写好的提示词和案例库（范例/）有没有成段相同的文字。

案例只用来学写法，不能照搬原文（规则见 范例/README.md「案例怎么用」）。
交付提示词前运行一次；有命中就改写那几段，再跑一遍直到干净。

用法：
  python3 tools/check_copy.py 草稿.md          # 检查一个文件
  python3 tools/check_copy.py - < 草稿.md       # 从标准输入读
  python3 tools/check_copy.py 草稿.md --min 20  # 改阈值（默认连续 25 字相同算命中）

去掉所有空白后比较。两类内容不算照抄：
- 规则库（.claude/skills/ 和 CLAUDE.md）里原有的句子，例如执行层要求每条都写的
  "严格按台词生成，禁止增减台词。无背景音乐，无字幕，无旁白"；
- 反引号里的库名和路径，例如 `exec-seedance25`。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "范例")


def norm(s):
    return re.sub(r"\s+", "", s)


def main():
    args = sys.argv[1:]
    n = 25
    if "--min" in args:
        i = args.index("--min")
        n = int(args[i + 1])
        del args[i:i + 2]
    if not args:
        print(__doc__)
        sys.exit(2)
    draft = sys.stdin.read() if args[0] == "-" else open(args[0], encoding="utf-8").read()
    draft = re.sub(r"`[^`\n]*`", "", draft)
    d = norm(draft)
    rules = ""
    for dp, _, fs in os.walk(os.path.join(ROOT, ".claude", "skills")):
        for f in fs:
            if f.endswith(".md"):
                rules += norm(open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read())
    rules += norm(open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read())
    # 先把草稿里和规则库原文重合 12 字以上的部分剔掉，换成断点，再拿剩下的去比案例
    m = 12
    covered = [False] * len(d)
    for i in range(len(d) - m + 1):
        if d[i:i + m] in rules:
            for k in range(i, i + m):
                covered[k] = True
    d = "".join("\x00" if c else ch for ch, c in zip(d, covered))
    cases = {}
    for dp, _, fs in os.walk(CASES):
        for f in fs:
            if f in ("README.md", "索引.md"):
                continue
            p = os.path.join(dp, f)
            cases[os.path.relpath(p, ROOT)] = norm(open(p, encoding="utf-8", errors="ignore").read())

    hits = []  # (start, end, case)
    i = 0
    while i + n <= len(d):
        w = d[i:i + n]
        src = None if "\x00" in w else next((c for c, t in cases.items() if w in t), None)
        if not src:
            i += 1
            continue
        j = i + n  # 尽量向后延伸，合并成一整段
        while j < len(d) and d[j] != "\x00" and d[i:j + 1] in cases[src]:
            j += 1
        hits.append((i, j, src))
        i = j

    if not hits:
        print(f"干净：没有连续 {n} 字以上与案例相同的段落。")
        return
    total = sum(e - s for s, e, _ in hits)
    print(f"命中 {len(hits)} 段，共 {total} 字与案例相同（占草稿 {total * 100 // max(len(d), 1)}%），请改写：")
    for s, e, src in hits:
        frag = d[s:e]
        print(f"- 来自 {src}：{frag[:60]}{'……' if len(frag) > 60 else ''}（{e - s} 字）")
    sys.exit(1)


if __name__ == "__main__":
    main()
