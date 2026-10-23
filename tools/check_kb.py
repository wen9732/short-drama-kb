#!/usr/bin/env python3
"""知识库结构校验：防止库变多之后结构失控。

检查项：
1. 每个技能有 frontmatter（name、description），name 与目录名一致
2. 层前缀合法
3. 有"## 边界"段
4. SKILL.md 不超过 200 行
5. CLAUDE.md 注册表与实际目录一致（启用的库都存在，存在的库都已登记）
6. 技能里引用的 `范例/...` 路径真实存在（支持 * 通配）
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

print(f"技能 {len(dirs)} 个：{', '.join(dirs)}")
for w in warnings:
    print("提示 ", w)
for e in errors:
    print("错误 ", e)
print("通过" if not errors else f"未通过：{len(errors)} 个错误")
sys.exit(1 if errors else 0)
