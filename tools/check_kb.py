#!/usr/bin/env python3
"""知识库结构校验：防止库变多之后结构失控。

检查项：
1. 每个技能有 frontmatter（name、description），name 与目录名一致
2. 层前缀合法
3. 有"## 边界"段
4. SKILL.md 不超过 200 行
5. CLAUDE.md 注册表与实际目录一致（启用的库都存在，存在的库都已登记）
6. 技能里引用的 `范例/...` 路径真实存在（支持 * 通配）
7. 案例库：每个案例都登记在所属类别的 索引.md；无画布元数据残留；范例之间、范例与原始素材之间无重复正文
用法：python3 tools/check_kb.py   （在仓库根目录运行）
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, ".claude", "skills")
PREFIXES = ("exec-", "script-", "perf-", "fight-", "cam-", "genre-")
MAX_LINES = 200

errors, warnings = [], []


def registry():
    text = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    names = {}
    for m in re.finditer(r"^\|\s*`([a-z]+-[a-z0-9*-]+)`\s*\|(.*)$", text, re.M):
        name, rest = m.group(1), m.group(2)
        if "*" in name:
            continue
        names[name] = "启用" in rest
    return names


reg = registry()
dirs = sorted(d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d)))

for d in dirs:
    path = os.path.join(SKILLS, d, "SKILL.md")
    if not os.path.exists(path):
        errors.append(f"{d}: 缺少 SKILL.md")
        continue
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    fm = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not fm:
        errors.append(f"{d}: 缺少 frontmatter")
    else:
        name = re.search(r"^name:\s*(.+)$", fm.group(1), re.M)
        desc = re.search(r"^description:\s*(.+)$", fm.group(1), re.M)
        if not name or name.group(1).strip() != d:
            errors.append(f"{d}: frontmatter name 与目录名不一致")
        if not desc:
            errors.append(f"{d}: 缺少 description")
    if not d.startswith(PREFIXES):
        errors.append(f"{d}: 层前缀不合法，应为 {PREFIXES}")
    if "## 边界" not in text:
        errors.append(f"{d}: 缺少「## 边界」段")
    if len(lines) > MAX_LINES:
        errors.append(f"{d}: {len(lines)} 行，超过 {MAX_LINES} 行上限，细节移到 references/")
    if d not in reg:
        errors.append(f"{d}: 未在 CLAUDE.md 注册表登记")
    for ref in re.findall(r"`(范例/[^`]+)`", text):
        if not glob.glob(os.path.join(ROOT, ref)):
            errors.append(f"{d}: 引用的范例不存在 → {ref}")
    if "暂存" in text:
        warnings.append(f"{d}: 含暂存段，对应库建成后记得迁出")

for name, active in reg.items():
    if active and name not in dirs:
        errors.append(f"注册表登记为启用，但目录不存在：{name}")

# ---- 案例库检查（规则见 范例/README.md）----
CASES = os.path.join(ROOT, "范例")
RAW = os.path.join(ROOT, "原始素材")
META = re.compile(r"^\s*(-\s*)?(原画布[:：]|画布链接[:：]|作品链接[:：]|工作区[:：]|参数[:：]|参考图清单[:：]|提示词全文|（注[:：]|## \d+\. 视频节点|### 视频 \d)")


def norm(s):
    return re.sub(r"\s+", "", s)


case_files = []
for dp, _, fs in os.walk(CASES):
    for f in fs:
        if f in ("README.md", "索引.md"):
            continue
        case_files.append(os.path.join(dp, f))

# 1. 每个案例都归在某个有索引的类别里，并被索引列出
for cf in case_files:
    d, owner = os.path.dirname(cf), None
    while d.startswith(CASES) and d != CASES:
        if os.path.exists(os.path.join(d, "索引.md")):
            owner = d
            break
        d = os.path.dirname(d)
    rel = os.path.relpath(cf, CASES)
    if not owner:
        errors.append(f"案例没有所属索引：范例/{rel}（类别目录缺 索引.md）")
        continue
    idx = open(os.path.join(owner, "索引.md"), encoding="utf-8").read()
    if f"`{os.path.relpath(cf, owner)}`" not in idx:
        errors.append(f"案例未登记到索引：范例/{rel} → 写进 {os.path.relpath(owner, ROOT)}/索引.md")

# 2. 画布元数据残留
for cf in case_files:
    for i, line in enumerate(open(cf, encoding="utf-8", errors="ignore"), 1):
        if META.match(line):
            errors.append(f"画布元数据残留：范例/{os.path.relpath(cf, CASES)} 第 {i} 行")
            break

# 3. 查重：范例之间、范例与原始素材
texts = {cf: norm(open(cf, encoding="utf-8", errors="ignore").read()) for cf in case_files}
seen = {}
for cf, t in texts.items():
    if t in seen:
        errors.append(f"范例重复：{os.path.relpath(cf, ROOT)} 与 {os.path.relpath(seen[t], ROOT)} 正文相同")
    seen.setdefault(t, cf)
raw = {}
for dp, _, fs in os.walk(RAW):
    for f in fs:
        if f.endswith((".md", ".txt")):
            p = os.path.join(dp, f)
            raw[p] = norm(open(p, encoding="utf-8", errors="ignore").read())
for cf, t in texts.items():
    body = t[:2000] if len(t) > 2000 else t
    if len(body) < 200:
        continue
    for p, rt in raw.items():
        if body in rt:
            errors.append(f"原始素材里存了范例的正文：{os.path.relpath(p, ROOT)} 含 {os.path.relpath(cf, ROOT)} → 改成指针")
            break

print(f"技能 {len(dirs)} 个：{', '.join(dirs)}")
for w in warnings:
    print("提示 ", w)
for e in errors:
    print("错误 ", e)
print("通过" if not errors else f"未通过：{len(errors)} 个错误")
sys.exit(1 if errors else 0)
