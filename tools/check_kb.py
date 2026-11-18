#!/usr/bin/env python3
"""知识库结构校验：防止库变多之后结构失控。

检查项：
1. 每个技能有 frontmatter（name、description），name 与目录名一致
2. 层前缀合法
3. 有"## 边界"段
4. SKILL.md 不超过 200 行
5. 维护手册.md 注册表与实际目录一致（启用的库都存在，存在的库都已登记）
6. 技能里引用的 `范例/...` 路径真实存在（支持 * 通配）
7. 案例库：每个案例都登记在所属类别的 索引.md；无画布元数据和点评残留；范例之间、范例与原始素材之间无重复正文
8. 工位卡与项目卡（v3.0）：列出的文件都存在；必读里没有 范例/ 和 原始素材/；按加载预算报出字数
用法：python3 tools/check_kb.py   （在仓库根目录运行）
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, ".claude", "skills")
PREFIXES = ("exec-", "script-", "perf-", "fight-", "cam-", "genre-", "art-", "audio-")
MAX_LINES = 200

errors, warnings = [], []


def registry():
    text = open(os.path.join(ROOT, "维护手册.md"), encoding="utf-8").read()
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
        errors.append(f"{d}: 未在 维护手册.md 注册表登记")
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
META = re.compile(r"^\s*(-\s*)?(>?\s*来源[:：]|>?\s*平台参数[:：]|原画布[:：]|画布链接[:：]|作品链接[:：]|工作区[:：]|参数[:：]|参考图清单[:：]|参考图使用清单[:：]|提示词全文|（注[:：]|## \d+\. 视频节点|### 视频 \d|>?\s*\**(用户评价|保留原因|为什么选它)[:：]|## (设计要点|执行风险|如果翻车|可调用的写法|可改进处|附：原文照录说明))|@\[?[0-9a-f-]{16,64}\]?|\{\{Mixed\s*\d+\}\}|〔[^〕]*参考图〕|〔在此|libtv-res\.liblib\.art")


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
    rel_idx = os.path.relpath(cf, owner).replace("\\", "/")
    if f"`{rel_idx}`" not in idx:
        errors.append(f"案例未登记到索引：范例/{rel} → 写进 {os.path.relpath(owner, ROOT)}/索引.md")

# 2. 画布元数据残留
for cf in case_files:
    for i, line in enumerate(open(cf, encoding="utf-8", errors="ignore"), 1):
        if META.search(line):
            errors.append(f"画布元数据、哈希串或点评残留（点评写进索引）：范例/{os.path.relpath(cf, CASES)} 第 {i} 行")
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


# ---- 导演库（规则见 cam-director 的 SKILL.md「新导演入库」）----
DIRLIB = os.path.join(SKILLS, "cam-director")
dir_report = None
if os.path.isdir(DIRLIB):
    ref = os.path.join(DIRLIB, "references")
    CODE = r"(?<![A-Za-z0-9])((?:HW|JP|KR|CN|EU|[A-Z]{2})\d{2}|M\d{2})(?!\d)"
    HEAD = re.compile(r"^### ([A-Z]{2}\d{2}|M\d{2}) (.+)$", re.M)
    TECH_FIELDS = ("出处", "机制", "用在", "Seedance 写法", "常配接缝", "别用在")
    MIND_FIELDS = ("问题", "做法", "出处", "落到设计", "反例")
    entries, verified = {}, 0

    def blocks(path):
        text = open(path, encoding="utf-8").read()
        heads = list(HEAD.finditer(text))
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            yield h.group(1), text[h.start():end]

    def field(body, name):
        m = re.search(r"^- \*\*" + re.escape(name) + r"：\*\*(.*?)(?=^- \*\*|\Z)", body, re.M | re.S)
        return m.group(1) if m else None

    tech_files = sorted(glob.glob(os.path.join(ref, "导演手法", "*.md")))
    mind_file = os.path.join(ref, "导演思维.md")
    for path, fields, is_mind in [(f, TECH_FIELDS, False) for f in tech_files] + [(mind_file, MIND_FIELDS, True)]:
        if not os.path.exists(path):
            errors.append(f"导演库缺文件：{os.path.relpath(path, ROOT)}")
            continue
        rel = os.path.relpath(path, ROOT)
        if not is_mind and len(open(path, encoding="utf-8").read()) > 7000:
            warnings.append(f"{rel}: 超过约 6000 字，新条目开下一份 -N.md")
        for code, body in blocks(path):
            if code in entries:
                errors.append(f"导演库编号重复：{code}（{rel} 与 {entries[code]}）")
            entries[code] = rel
            if is_mind != code.startswith("M"):
                errors.append(f"{rel}: {code} 放错了文件（M 编号只放导演思维.md）")
            for fn in fields:
                v = field(body, fn)
                if v is None or not v.strip():
                    errors.append(f"{rel}: {code} 缺「{fn}」")
            src = field(body, "出处") or ""
            if "【已核】" in src:
                verified += 1
            elif "【公认】" not in src:
                errors.append(f"{rel}: {code} 的出处没有标【已核】或【公认】")

    # 编号 → 文件 对照（总表第三节）
    table = os.path.join(ref, "导演库总表.md")
    ttext = open(table, encoding="utf-8").read() if os.path.exists(table) else ""
    ranges = []
    for m in re.finditer(r"([A-Z]{2})(\d{2})–[A-Z]{2}(\d{2}) → `([^`]+)`", ttext):
        ranges.append((m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)))
    for m in re.finditer(r"(?<![A-Z])([A-Z]{2}) → `([^`]+)`", ttext):
        ranges.append((m.group(1), 0, 99, m.group(2)))
    for code, rel in entries.items():
        if code.startswith("M"):
            continue
        pre, num = code[:2], int(code[2:])
        want = [r[3] for r in ranges if r[0] == pre and r[1] <= num <= r[2]]
        if not want:
            errors.append(f"导演库总表第三节没写 {code} 在哪个文件")
        elif os.path.basename(rel) not in want:
            errors.append(f"{code} 在 {os.path.basename(rel)}，总表第三节写的是 {want[0]}")

    # 名录：每条手法都登记，登记的都存在
    skill_text = open(os.path.join(DIRLIB, "SKILL.md"), encoding="utf-8").read()
    roster = re.search(r"## 导演名录\n(.*?)(?=\n## )", skill_text, re.S)
    listed = set(re.findall(CODE, roster.group(1))) if roster else set()
    for code in entries:
        if not code.startswith("M") and code not in listed:
            errors.append(f"导演名录（cam-director SKILL.md）没有登记 {code}")
    for code in listed - set(entries):
        errors.append(f"导演名录登记了不存在的条目：{code}")

    # 引用检查：导演库各文件与导演语法里引用的编号都要存在；转场编号要在转场全集里
    tfile = os.path.join(SKILLS, "cam-transitions", "references", "转场全集.md")
    tcodes = set(re.findall(r"^### (T\d{2})", open(tfile, encoding="utf-8").read(), re.M)) if os.path.exists(tfile) else set()
    scan = glob.glob(os.path.join(DIRLIB, "**", "*.md"), recursive=True) + [
        os.path.join(SKILLS, "exec-seedance25", "references", "导演语法.md")]
    for path in scan:
        if not os.path.exists(path):
            continue
        text = re.sub(r"```.*?```", "", open(path, encoding="utf-8").read(), flags=re.S)  # 模板代码块不算引用
        rel = os.path.relpath(path, ROOT)
        for code in set(re.findall(CODE, text)):
            if code not in entries:
                errors.append(f"{rel}: 引用了不存在的导演库编号 {code}")
        if tcodes:
            for t in set(re.findall(r"(?<![A-Za-z0-9-])(T\d{2})(?!\d)", text)):
                if t not in tcodes:
                    errors.append(f"{rel}: 引用了不存在的转场编号 {t}")
    tech = [c for c in entries if not c.startswith("M")]
    dir_report = f"导演库：手法 {len(tech)} 条、思维 {len(entries) - len(tech)} 条；出处含【已核】的 {verified} 条，其余为【公认】"


# ---- 工位卡与项目卡（规则见 维护手册.md 第三节）----
MUST_LIMIT, TOTAL_LIMIT = 50000, 65000
PATH = re.compile(r"`([^`<>*]+\.(?:md|txt))`")


def chars(rel):
    return len(open(os.path.join(ROOT, rel), encoding="utf-8").read())


def sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(\S+)", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return out


entry = "启动.md"
if not os.path.exists(os.path.join(ROOT, entry)):
    errors.append("缺少总入口 启动.md")
else:
    for rel in PATH.findall(open(os.path.join(ROOT, entry), encoding="utf-8").read()):
        if not rel.startswith(("python3",)) and "/" in rel and not os.path.exists(os.path.join(ROOT, rel)):
            errors.append(f"启动.md 引用的文件不存在：{rel}")

cards = sorted(glob.glob(os.path.join(ROOT, "工位", "*.md"))) + sorted(glob.glob(os.path.join(ROOT, "项目", "*", "启动.md")))
base = chars(entry) if os.path.exists(os.path.join(ROOT, entry)) else 0
report = []
for c in cards:
    rel_c = os.path.relpath(c, ROOT)
    raw_card = open(c, encoding="utf-8").read()
    for h in re.findall(r"^##\s+((?:必读|按需)\S+.*)$", raw_card, re.M):
        errors.append(f"{rel_c}: 段名「{h}」后面不能带字（否则字数统计会漏掉这一段），说明写到下一行")
    sec = sections(raw_card)
    if "必读" not in sec:
        errors.append(f"{rel_c}: 缺少「## 必读」段")
        continue
    must = []
    for line in sec["必读"]:
        must += PATH.findall(line)
    for p in must:
        if p.startswith(("范例/", "原始素材/")):
            errors.append(f"{rel_c}: 必读里不许有案例或原始素材 → {p}（改成按需，点名才读）")
    opts = []
    for line in sec.get("按需", []):
        ps = PATH.findall(line)
        if ps:
            opts.append(ps)
    for p in must + [x for o in opts for x in o]:
        if not os.path.exists(os.path.join(ROOT, p)):
            errors.append(f"{rel_c}: 列出的文件不存在 → {p}")
    try:
        m_sum = base + chars(rel_c) + sum(chars(p) for p in dict.fromkeys(must))
        heavy = max((sum(chars(p) for p in dict.fromkeys(o) if p not in must) for o in opts), default=0)
    except FileNotFoundError:
        continue
    report.append((rel_c, m_sum, m_sum + heavy))
    if m_sum > MUST_LIMIT:
        errors.append(f"{rel_c}: 必读 {m_sum} 字，超过 {MUST_LIMIT} 字预算 → 拆文件或挪到按需")
    elif m_sum + heavy > TOTAL_LIMIT:
        warnings.append(f"{rel_c}: 必读加最重一档按需 {m_sum + heavy} 字，超过 {TOTAL_LIMIT} 字")

# 验错工具自检：错误库里能机器查的规则还管用
sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    import check_errors
    if not check_errors.selftest():
        errors.append("tools/check_errors.py 自检失败（见上方输出）")
except Exception as ex:  # noqa: BLE001
    errors.append(f"tools/check_errors.py 无法运行：{ex}")

print(f"技能 {len(dirs)} 个：{', '.join(dirs)}")
if dir_report:
    print(dir_report)
if report:
    print("工位加载量（含 启动.md 和卡片本身）：")
    for rel_c, m_sum, top in report:
        print(f"  {rel_c}：必读 {m_sum} 字；最重一档 {top} 字")
for w in warnings:
    print("提示 ", w)
for e in errors:
    print("错误 ", e)
print("通过" if not errors else f"未通过：{len(errors)} 个错误")
sys.exit(1 if errors else 0)
