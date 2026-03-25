AlphaFlow
=========

AlphaFlow 是一个面向金融因子研发与研报驱动因子抽取的工具套件，旨在把研究员从研报中的想法快速转化为可执行的因子实现、回测评估并保存可复现的实验产物。

项目定位与原创性
-----------------
- AlphaFlow 在架构上借助并兼容 `qlib` 的数据与回测能力，同时对原有 `RD-Agent` 框架做了定制化改造（工作区执行、因子注入与任务编排等），因此本项目是基于 `qlib` 与 `RD-Agent` 的开发改造并包含若干原创实现：
  - 自定义的 `FactorFBWorkspace` 执行/注入机制（将自动生成的 `factor.py` 作为算子运行并标准化输出 `result.h5`）。
  - 报告可视化与会话持久化机制（上传报告的缩略图/文本摘录与缓存，以支持刷新/复用）。
  - 面向研究员的交互式任务启动器，包含因子合并、去重、并行迭代控制与回测触发逻辑。

核心功能模块
-------------
- `fin_factor`（因子挖掘引擎）
  - 负责批量运行因子实验与回测：接收因子实现脚本（`factor.py`）、合并新旧因子、对新因子做去重与筛选、调用 qlib 回测并收集评估指标（如 IC/年化收益等）。
  - 支持多轮迭代（`loop_n`）与步级调试（`step_n`），并能把结果持久化到 `log/` 目录下用于审计与回放。

- `report`（研报驱动因子抽取）
  - 支持从 PDF/JSON 等研报中提取因子定义与自然语言描述，通过 LLM 或规则化模板生成可执行的 `factor.py`，并允许用户在 UI 内预览、编辑与确认。
  - 将用户确认的报告与自动生成的实现注入任务工作区，便于后续执行、复现与人工审查。

新增交互与可视化功能（本次交付）
--------------------------------
- 报告预览小窗：上传后在 UI 右侧展示报告第一页缩略图与文本摘要，支持快速核验内容。
- 上传持久化：将上传报告标准化并缓存在会话状态中，刷新页面后仍可复用并传递到任务启动器。
- 提示词输入与引导：任务启动器提供提示词（prompt）输入框，研究员可通过自然语言提示引导 LLM 生成或改写因子实现逻辑。
- 任务参数化：UI 支持设置 `loop_n`（完整回合数）、`step_n`（全局步数限制）、选择/注入报告并一键启动 `fin_factor` / `report` 流程。

快速开始
---------
1. 推荐在虚拟环境中安装依赖：
```bash
pip install -r requirements.txt
# UI 运行需求（若使用 Streamlit UI）：
pip install streamlit PyMuPDF
```
2. 启动 Streamlit UI：
```bash
streamlit run rdagent/log/ui/main.py --server.headless true --server.port 8501
```
3. 操作流程：
  - 进入 UI，上传研报并在右侧预览；
  - 在任务启动器中选择目标（`fin_factor` 或 `report`）、设置 `loop_n`/`step_n`、输入提示词；
  - 点击启动，任务日志与产物保存在 `log/` 下对应目录。

项目结构（速览）
-----------------
- `rdagent/components/coder/factor_coder`：因子任务与工作区执行器，实现 `FactorTask` 与 `FactorFBWorkspace`。 
- `rdagent/scenarios/qlib`：与 qlib 集成的实验模板、loader 与 runner，用于将因子数据打包为 qlib 可执行格式并触发回测。 
- `rdagent/log/ui`：Streamlit 前端实现、报告预览、任务启动器与报告持久化逻辑。

