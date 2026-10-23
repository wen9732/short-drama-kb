# 更新记录

## 2026-10-23 剧本层与表演层打通
- CLAUDE.md 新增「完整流水线」：剧本 → 转换 → 回流。
- `script-shanyin` 边界新增：写剧本时可借用 `perf-` 的可见行为写法；剧本交付后的下一步加"转成 Seedance 提示词"。

## 2026-10-23 剧本层接入
- 新增 `script-shanyin`（山音超级编剧大师 v2 通用版·维护修订），填补剧本层。仅改 frontmatter name 并新增「边界」一节，作者正文未改动；原包存档于 `原始素材/script-shanyin/`。
- CLAUDE.md 新增跨层约定：剧本稿与提示词稿的括号规则；"情绪直给"属剧情层。

## 2026-10-23 系统提示词
- 新增 `系统提示词/短剧情绪导演_System_Prompt_V2.0_强制毒舌版.md`：以 V1.1 为骨架，写入情绪五拍、AI感八来源、两种表演模式、Seedance 2.5 规范、强制毒舌协议，附五个完整范例（改写示范、毒舌批改、雨夜伞戏、最后一杯、空枪）。

## 2026-10-23 架构 v2：分层
- 建立六层架构（exec / script / perf / fight / cam / genre），每个库只管一个维度，写入 CLAUDE.md。
- 改名：`seedance25-spec` → `exec-seedance25`，`drama-restrained` → `perf-restrained`，`korean-noir-explosive` → `perf-explosive`。
- 拆分：原 `korean-noir-explosive` 混有表演、镜头、视觉三类规则，拆为 `perf-explosive`（表演）与 `genre-korean-noir`（视觉/氛围/韩语习惯）；荷兰角等镜头规则暂存在 `genre-korean-noir`，运镜库建成后迁出。
- `exec-seedance25` 模板为每个槽位标注负责层。
- 新增 `_模板/SKILL模板.md`、`tools/check_kb.py`（结构校验）。
- 目录改名：`范例/克制型` → `范例/表演-克制型`，`范例/爆发型` → `范例/表演-爆发型`；原始素材移入 `原始素材/综合/`。

## 2026-10-23 初始化
- 三个技能、范例 11 份、画布导出包存档。
