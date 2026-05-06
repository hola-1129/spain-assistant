# 部署到 GitHub Pages

`output/` 目录是一个完整的静态站点，所有链接相对路径，无后端依赖、无登录、无敏感信息。可以发布到 GitHub Pages 给家长访问。

## 推荐方案：output 作为独立仓库

让 `output/` 成为一个独立的 git 仓库（与 ai_workspace 主仓库分开），这样既不会把代码/缓存推到 Pages，也方便 git 推送时只动 `output/` 内容。

### 一次性初始化

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/school_helper/output

# 初始化独立仓库
git init -b main
git config user.email "你的邮箱"
git config user.name "Leslie"

# 屏蔽缓存目录（PDF 缓存不发布）
echo "cache/" > .gitignore

# 添加 GitHub 远程仓库（先在 GitHub 上新建一个空 repo，例如 brains-school-briefing）
git remote add origin git@github.com:<你的用户名>/brains-school-briefing.git

# 首次提交
git add .gitignore index.html school_events.ics events/ \
        weekly_briefing_cn.md weekly_briefing_summary.txt \
        extracted_links.json processing_log.txt
git commit -m "Initial briefing"
git push -u origin main
```

然后到 GitHub 仓库 **Settings → Pages**：
- Source: `Deploy from a branch`
- Branch: `main` / `/ (root)`
- 保存

几分钟后即可访问：`https://<你的用户名>.github.io/brains-school-briefing/`

### 每周更新

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/school_helper

# 1. 新 PDF 放进 input/
cp ~/Downloads/Briefing_*.pdf input/

# 2. 重新生成
.venv/bin/python main.py

# 3. 推送 output/
cd output
git add -A
git commit -m "Weekly update: $(date +%Y-W%V)"
git push
```

GitHub Pages 通常 1–2 分钟内自动重建。

## 替代方案：用主仓库的 docs/ 子目录

如果不想拆仓库，也可以把 `output/` 的内容拷贝到主仓库的 `docs/` 下，再在 Pages 设置里选 `main / docs`。但这会把 ai_workspace 主仓库推到 GitHub，可能不是你想要的（涉及代码、其它 agent、笔记等）。

## 自定义域名（可选）

如果你有自己的域名，可以在 `output/` 下加一个 `CNAME` 文件：

```bash
echo "school.lau.family" > output/CNAME
```

然后在域名提供商处添加 DNS 记录指向 GitHub Pages（CNAME → `<你的用户名>.github.io`）。

## 隐私自查清单

每次 push 之前确认：

- [ ] `output/cache/` 已 git-ignored（里面是学校 PDF 原件）
- [ ] `index.html` 不含 `/Volumes/` 路径（搜一下 `grep "/Volumes" output/*.html` 应为空）
- [ ] `processing_log.txt` 输入 PDF 字段只是文件名，不是绝对路径
- [ ] `.env`、API key 不在 `output/` 里（应该不会，但建议每次 push 前 grep `sk-ant`）

```bash
# 一行体检
grep -rE "/Volumes/|sk-ant-|ANTHROPIC" output/ && echo "⚠️ 发现敏感内容" || echo "OK"
```

## 历史版本

`output/archive/<YYYY-Www>/index.html` 是上一周的快照。如果你 push 了 `output/` 整目录，这些 archive 也会跟着发布，家长可以通过直接 URL 访问历史周次：
`https://<你的用户名>.github.io/brains-school-briefing/archive/2026-W18/`
