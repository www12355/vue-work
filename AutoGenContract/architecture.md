# AutoGenContract — 项目架构文档

## 概述

AI 驱动的通用型合同智能生成系统。用户上传参考文件、填写表单信息，系统自动生成包含 13 章节的完整中文服务合同（DOCX），同时输出质量审查报告和工作量统计报告。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + `marked` (Markdown 渲染) |
| 后端 | FastAPI + Uvicorn (端口 8002) |
| LLM | DeepSeek API (OpenAI-compatible, 流式调用) |
| 文档 | python-docx (DOCX 生成), PyPDF2, python-pptx |
| 通信 | REST API + WebSocket (实时进度推送) |

## 目录结构

```
自动合同生成/
├── server/                 # FastAPI 后端
│   ├── main.py             # 应用入口, CORS, 路由注册
│   ├── models.py           # Pydantic 模型, 阶段定义
│   ├── session_manager.py  # 会话生命周期管理
│   ├── ws_manager.py       # WebSocket 连接管理
│   ├── contract_adapter.py # 5阶段流水线编排（核心）
│   ├── routes_contract.py  # 会话创建/启动 API
│   ├── routes_upload.py    # 文件上传/管理/内容 API
│   ├── routes_download.py  # 会话列表/下载/DOCX转PDF
│   ├── routes_ws.py        # WebSocket 端点
│   └── routes_profile.py   # 全局参考文件管理
├── src/                    # 核心库
│   ├── llm/
│   │   ├── deepseek_client.py  # DeepSeek API 客户端
│   │   ├── prompt_builder.py   # Prompt 组装（上下文注入）
│   │   └── prompts.py          # Prompt 模板
│   ├── document/
│   │   ├── generator.py        # DOCX 生成器（Markdown→Word 状态机）
│   │   ├── reader.py           # 多格式文档读取（DOCX/PDF/PPTX）
│   │   └── replacer.py         # 旧版模板替换（保留兼容）
│   ├── config/loader.py        # YAML 配置加载
│   └── utils/date_utils.py     # 中文日期处理
├── lib/                    # 支持库
│   ├── skill_manager.py    # Skill 加载与 Prompt 构建
│   └── state_manager.py    # 流水线状态持久化
├── skills/                 # AI Skill 定义 (SKILL.md)
│   ├── contract-generate/  # 合同内容生成
│   ├── contract-review/    # 质量审查
│   ├── contract-statistics/# 工作量统计
│   └── contract-all/       # 旧版一体式 Skill
├── templates/              # 参考模板
│   ├── contract_template.md
│   └── template.docx
├── source/                 # 参考文档
├── 合同案例/                # 历史合同案例
├── workspaces/sessions/    # 会话工作区（运行时）
├── config.yaml             # DeepSeek API 配置
└── pipeline_config.yaml    # 流水线阶段配置
```

## 前端目录

```
AutoGenContract/
└── src/
    ├── App.vue                  # 根组件, 3面板 IDE 布局
    ├── components/
    │   ├── ContractForm.vue     # 合同表单 + 文件上传
    │   ├── ProgressCards.vue    # 流水线进度（左面板）
    │   ├── ProgressCard.vue     # 单阶段卡片
    │   ├── DocumentViewer.vue   # Markdown/PDF 查看器（中面板）
    │   ├── DownloadPanel.vue    # 下载面板
    │   ├── FileExplorer.vue     # 文件浏览器（右面板）
    │   ├── FileTreeNode.vue     # 递归文件树节点
    │   ├── HistoryList.vue      # 历史会话列表
    │   └── ProfileManager.vue   # 全局参考文件管理
    └── composables/
        ├── useContract.js       # 表单状态 + 实时上传
        ├── usePipeline.js       # 流水线状态管理
        ├── useWebSocket.js      # WebSocket 连接
        ├── useFileExplorer.js   # 文件树状态
        └── useHistory.js        # 历史记录状态
```

## 数据流

```
用户操作                         后端处理                        输出
───────                         ────────                        ────

1.选文件 → 自动上传 → workspaces/sessions/{id}/uploads/
                                      + profile/
                                      + templates/
2.填表单 → POST /api/session → 创建会话
3.点生成 → POST /api/session/{id}/start
                ↓
        WebSocket /ws/{id} ──→ 前端实时进度
                ↓
        Stage 0: 文件收集（读取 uploads/profile/templates）
        Stage 1: 合同生成（DeepSeek → 13章 Markdown）
        Stage 2: 质量审查（DeepSeek 并行）
        Stage 3: 工作量统计（DeepSeek 并行）
        Stage 4: 文档导出（Markdown → DOCX + 报告）
```

## 会话工作区结构

```
workspaces/sessions/{uuid}/
├── contract_config.json      # 表单数据
├── uploads/                  # 核心文件（用户上传）
│   └── user_input.md         # 用户文本输入
├── profile/                  # 参考文件（用户上传）
├── templates/                # 合同模板（自动复制）
│   └── contract_template.md
├── 01_config/                # Stage 0 缓存
├── 02_examples/              # Stage 1 缓存
│   ├── uploads/              # 核心文件缓存
│   └── profile/              # 参考文件缓存
├── 03_contract/              # Stage 2 缓存
│   ├── contract_full.md
│   ├── review_report.md
│   └── statistics.md
├── 04_output/                # 最终输出
│   ├── {合同编号}.docx
│   ├── {合同编号}_审查报告.md
│   └── {合同编号}_工作量统计.md
├── .temp/                    # 临时文件（PDF 缓存等）
└── pipeline_state.json       # 流水线状态
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/session | 创建会话（不启动） |
| POST | /api/session/{id}/upload | 上传文件（?type=uploads\|profile） |
| POST | /api/session/{id}/start | 启动流水线 |
| GET  | /api/session/{id}/cache-tree | 文件树 JSON |
| GET  | /api/session/{id}/file-content | 文件内容 |
| GET  | /api/session/{id}/docx-as-pdf | DOCX→PDF 转换 |
| GET  | /api/sessions | 历史会话列表 |
| GET  | /api/download/{id}/{file} | 文件下载 |
| WS   | /ws/{id} | WebSocket 进度推送 |

## 关键设计决策

1. **三步上传流程**：创建会话 → 上传文件 → 启动生成。文件在"开始生成"之前就已上传完毕，确保流水线能读到完整数据。

2. **状态机 DOCX 生成**：`generator.py` 使用 NORMAL/TABLE/CODE 三状态解析器，将 Markdown 转为格式化 Word 文档，支持表格、加粗、代码块。

3. **WebSocket 进度推送**：流水线每个阶段的开始/完成/失败都通过 WS 实时推送到前端，前端在 3 面板 IDE 布局中展示进度。

4. **Session 隔离**：每个会话独立的 `workspaces/sessions/{uuid}/` 目录，24小时 TTL 自动清理。

5. **并行优化**：合同质量审查（Stage 2）和工作量统计（Stage 3）并行执行，减少总耗时。
