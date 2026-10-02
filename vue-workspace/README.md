# AICC 工作台 · Vue 3 版

Next.js 工作台页面（`/workspace`）的独立 Vue 3 实现，功能与交互 1:1 还原。技术栈：Vite + Vue 3（`<script setup>` + TypeScript）+ Tailwind CSS v4 + lucide-vue-next。

## 运行

```bash
cd vue-workspace
pnpm install
pnpm dev     # 开发
pnpm build   # 类型检查 + 生产构建
```

## 目录结构

```
vue-workspace/
├─ index.html
├─ vite.config.ts
├─ public/images/            # 四张功能卡配图（从 Next 项目复制）
└─ src/
   ├─ main.ts
   ├─ style.css              # 设计令牌、背景网格、弹窗动画
   ├─ App.vue                # 页面骨架：网格背景 + 导航 + 工作区
   ├─ data/apps.ts           # AppId / 功能元数据 / 组合时长等常量
   └─ components/
      ├─ Navbar.vue          # 顶部导航（含浅/深色切换）
      ├─ BottomHero.vue      # 底部大标题与统计数字
      ├─ Workspace.vue       # 核心：拖拽、停靠、组合计时、弹窗调度
      ├─ HeroCard.vue        # 主卡片（放置区 / 停靠态展示）
      ├─ FunctionCard.vue    # 可拖拽功能卡（含右下挖角按钮）
      ├─ PlaceholderCard.vue # 待开发占位卡
      ├─ AppWindow.vue       # 居中功能弹窗（Esc 关闭、锁滚动）
      └─ apps/               # 标书 / 纪要 / 组合 / 合同 四个功能表单
```

## 交互还原说明

- **拖拽载入**：功能卡使用 Pointer Events，移动超过 8px 才判定为拖拽；松手时若指针位于主卡片矩形内则停靠该功能。
- **播放 / 暂停**：功能卡右下角按钮直接切换停靠状态；组合态下暂停其中一个会保留另一个。
- **组合模式**：仅「标书 × 会议纪要」可组合。已停靠其一时，拖动另一张卡在主卡片上持续悬停 5 秒（`requestAnimationFrame` 环形进度）即触发 `combo`。
- **状态管理**：全部状态用 `ref` 收敛在 `Workspace.vue`，未引入 Pinia，便于直接嵌入其他 Vue 工程。

## 迁移对照

| React | Vue 3 |
| --- | --- |
| `useState` | `ref` |
| `useRef`（DOM） | 模板 `ref` |
| `useRef`（可变值） | 组件作用域普通变量 |
| `useCallback` | 普通函数 |
| `children` / render prop | `<slot name="bottom">` |
| 条件渲染三元表达式 | `v-if` / `v-else` |
| `Record` 映射渲染组件 | `<component :is="...">` |
