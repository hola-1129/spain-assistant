# school_helper HTML 页面规范

## 视觉要求（强制执行，不可回退）

### Header
- 左侧显示 Brains School logo（`./logo_brains.png`，height: 52px）
- logo 为品牌蓝 `#006AB4` RGBA PNG，非灰度图
- 右侧显示标题 "Weekly Briefing · 中文家长版" + meta 行
- 无"一键添加全部日历"按钮

### 年级色彩系统
每个年级有唯一 CSS custom property `--grade` 颜色：

| 年级 | CSS class | 颜色 |
|------|-----------|------|
| 全校通用 | grade-general | #7c3aed |
| Infantil / 幼儿园 | grade-infantil | #db2777 |
| Primaria / 小学 | grade-primaria | #0b66c2 |
| Preparatory | grade-preparatory | #0891b2 |
| ESO / 中学 | grade-eso | #16a34a |
| Bachillerato / 高中 | grade-bachillerato | #d97706 |
| IBDP | grade-ibdp | #dc2626 |

### 年级标识必须出现在以下所有位置
1. **按年级分类** 区块：
   - `<h3>` 带 `class="grade-h {gc}"` → 左边框 + 文字颜色
   - 每个事件卡片：有年级时加 `has-grade {gc}` 类 + grade-pill 徽章
2. **本周重点** 区块：每条目标题前加 `<span class="grade-pill {gc}">年级名</span>`
3. **家长需要操作** 区块：每条目标题前加 `<span class="grade-pill {gc}">年级名</span>`
4. **事件卡片**（`_event_card`）：已有，保持

### 翻译规则
- 所有 `title_cn` 空值 → 显示 `"(无中文标题)"`，禁止 fallback 到西班牙语原标题
- 原文链接区：`title_cn / title_es` 双语（有中文时），无中文时只显示 title_es
- 日历区：同上

### 学校视角分析（school_intent_cn）
- LLM 抽取字段，2-3 句话，从学校管理者视角分析通知的真实目的
- 不复述内容，分析动机：收费、获取同意、宣传形象、法定告知、申请补贴配合、展示成果等
- 渲染在原文摘录之前，用黄色左边框 `.intent-box` 样式
- HTML: `<div class="intent-box"><span class="intent-label">💡 学校视角：</span>...</div>`
- Markdown: `💡 **学校视角**：{school_intent_cn}`（写入 weekly_briefing_cn.md）

### Google Maps 按钮
- 有 `location_cn` 或 `location_es` 且不为 `"(原文未说明)"` 时，显示蓝色 Maps 按钮
- URL: `https://www.google.com/maps/search/?api=1&query=<encoded>+Madrid`

### 已删除
- 黄历 / 节假日 整个区块（永久删除）
- almanac_data 传参保留但不渲染

## 技术修复

### archive_previous
- `shutil.rmtree(events_dst, ignore_errors=True)` 避免 macOS AppleDouble 文件崩溃

### logo_brains.png 生成方式
下载官网灰度 PNG 后，用 Pillow 重新着色为品牌蓝 `#006AB4`：
```python
new_alpha = (alpha * (1.0 - gray / 255.0)).clip(0, 255).astype(np.uint8)
out[:,:,0]=0; out[:,:,1]=106; out[:,:,2]=180; out[:,:,3]=new_alpha
```
