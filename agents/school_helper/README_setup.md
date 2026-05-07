# School Helper — Email Watcher 自动化部署

让 Mac 周一至周五 9:00–22:00 每 30 分钟检查一次 Gmail，发现学校
（`comunicaciones@esemtia.com`）的新邮件就：

- 有 PDF 附件 → 下载 → 跑 `main.py` → push 到 GitHub Pages → Telegram 通知 ✅
- 无 PDF 附件 → 邮件正文转发到 Telegram

---

## 一次性设置（约 10 分钟）

### 1. 安装 Python 依赖

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/school_helper
.venv/bin/pip install -r requirements.txt
```

### 2. 在 Google Cloud 注册 OAuth client

> Gmail API 必须走 OAuth；不能用 App Password。一次性配置，refresh token 长期有效。

1. 打开 https://console.cloud.google.com/projectcreate ，新建项目（建议名字 `school-helper`）
2. 进入新项目 → 左侧菜单 **APIs & Services → Library** → 搜索 `Gmail API` → 点 **Enable**
3. 左侧菜单 **APIs & Services → OAuth consent screen**
   - User Type 选 **External** → Create
   - App name: `school-helper`
   - User support email / Developer contact: `ning.lau@gmail.com`
   - Save and continue 直到回到首页
   - **Test users** 里加入 `ning.lau@gmail.com`（很关键，否则不让授权）
4. 左侧菜单 **APIs & Services → Credentials**
   - 点 **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Name 随便（如 `school-helper-cli`）→ Create
   - 弹窗里点 **Download JSON**，把文件**重命名为 `credentials.json`**，放到：
     ```
     /Volumes/AI_DISK/ai_workspace/agents/school_helper/credentials.json
     ```

### 3. 首次授权（生成 token.json）

在 Mac 上**有图形界面**时执行（会自动打开浏览器）：

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/school_helper
.venv/bin/python email_watcher.py --auth
```

浏览器跳出 → 选 `ning.lau@gmail.com` → 警告"未验证 app"点 **Advanced → Go to school-helper (unsafe)** → 同意"读取 Gmail" 权限。

终端打印 `OAuth 授权成功，token 写入 token.json` 即可。

### 4. 干跑验证（不真改文件、不发 TG）

```bash
.venv/bin/python email_watcher.py --dry-run
```

应该看到：`扫描完成: 总计 N 封符合条件，新邮件 M 封` 之类。

### 5. 一次真跑（强制处理某封历史邮件）

如果想立刻拉一遍最近的 briefing 测试效果（不等下一封新邮件）：

```bash
# 不带 --force 直接跑，会处理所有未在 state.json 里的新邮件
.venv/bin/python email_watcher.py
```

或者强制处理某个 `message_id`（在 Gmail URL `?th=...` 里能看到内部 ID）：

```bash
.venv/bin/python email_watcher.py --force-msg-id <id>
```

成功后 Telegram 会收到 ✅ 消息，GitHub Pages 自动重建。

### 6. 加载 launchd 定时任务

```bash
# 复制 plist 到用户级 LaunchAgents（每次登录自动加载）
cp /Volumes/AI_DISK/ai_workspace/scripts/launchd/com.leslie.school_helper.plist \
   ~/Library/LaunchAgents/

# 立刻加载，无需重新登录
launchctl load ~/Library/LaunchAgents/com.leslie.school_helper.plist

# 验证已加载
launchctl list | grep school_helper
```

---

## 日常运维

### 看实时日志

```bash
tail -f /Volumes/AI_DISK/ai_workspace/logs/school_helper/email_watcher.log
tail -f /Volumes/AI_DISK/ai_workspace/logs/school_helper/launchd.err.log
```

### 暂停 / 恢复

```bash
launchctl unload ~/Library/LaunchAgents/com.leslie.school_helper.plist   # 暂停
launchctl load   ~/Library/LaunchAgents/com.leslie.school_helper.plist   # 恢复
```

### 重置已处理列表（让历史邮件重跑）

```bash
rm /Volumes/AI_DISK/ai_workspace/agents/school_helper/state.json
```

### token 过期了

正常情况 refresh token 不会过期。如果 6 个月没用、或者你在 Google
Account 撤销了授权，会失效。**症状**：Telegram 收到 "❌ 邮件处理异常"，
日志里有 `RefreshError`。修复：

```bash
rm /Volumes/AI_DISK/ai_workspace/agents/school_helper/token.json
.venv/bin/python email_watcher.py --auth
```

---

## 文件清单

| 文件 | 说明 | 是否提交 git |
|---|---|---|
| `email_watcher.py` | 主脚本 | 是 |
| `notifier.py` | Telegram 封装 | 是 |
| `credentials.json` | Google OAuth client 配置 | **否** |
| `token.json` | refresh token | **否** |
| `state.json` | 已处理 message_id | **否** |
| `scripts/launchd/com.leslie.school_helper.plist` | launchd 配置模板 | 是 |

`credentials.json` / `token.json` / `state.json` 已加入 `.gitignore`，
不会被推到任何远端仓库。Telegram 凭证从 `agents/finance_bot/.env` 自动读取，无需重复配置。
