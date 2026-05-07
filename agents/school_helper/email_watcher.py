#!/usr/bin/env python3
"""Email watcher — 周期性检测来自学校的邮件，自动跑 pipeline 并发布。

工作流（每次 launchd 唤起一次）：
  1. Gmail API 用 OAuth 凭证拉取 from:<sender> 最近 N 天未处理的邮件
  2. 对每封新邮件：
       - 有 PDF 附件 → 写到 input/，调 main.py 生成站点，git push 到 GitHub Pages，
         Telegram 推 "✅ 已更新 + URL"
       - 无 PDF 附件 → Telegram 推主题 + 正文摘录，让用户决定是否手工处理
  3. 把 message_id 记到 state.json，避免重复触发

凭证：
  - credentials.json (Google Cloud 下载的 OAuth client) — 必需
  - token.json (首次 OAuth flow 后生成的 refresh token) — 自动维护

首次跑（终端交互式授权）：
  python email_watcher.py --auth

之后正常调度：
  python email_watcher.py
"""

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import load_config
from notifier import Notifier
from utils.logger import setup_logger

logger = setup_logger("email_watcher")

_HERE = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDS_FILE = _HERE / "credentials.json"
TOKEN_FILE = _HERE / "token.json"
STATE_FILE = _HERE / "state.json"


# ---------- state ----------

def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"processed_message_ids": []}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning(f"state.json 损坏，重建")
        return {"processed_message_ids": []}


def _save_state(state: dict) -> None:
    # 只保留最近 200 条 message_id，避免无限增长
    ids = state.get("processed_message_ids", [])
    state["processed_message_ids"] = ids[-200:]
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------- gmail auth ----------

def _get_gmail_service():
    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
        else:
            if not CREDS_FILE.exists():
                raise FileNotFoundError(
                    f"未找到 {CREDS_FILE}。请先按 README_setup.md 配置 Google OAuth。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
            TOKEN_FILE.write_text(creds.to_json())
            logger.info(f"OAuth 授权成功，token 写入 {TOKEN_FILE}")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ---------- gmail fetch ----------

def _list_messages(service, sender: str, lookback_days: int) -> list[str]:
    query = f"from:{sender} newer_than:{lookback_days}d"
    msgs: list[dict] = []
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, pageToken=page_token, maxResults=50,
        ).execute()
        msgs.extend(resp.get("messages", []) or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return [m["id"] for m in msgs]


def _get_message(service, msg_id: str) -> dict:
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _walk_parts(payload: dict):
    """深度遍历 payload，yield 每个 part。"""
    yield payload
    for child in payload.get("parts", []) or []:
        yield from _walk_parts(child)


def _extract_body_text(payload: dict) -> str:
    """优先取 text/plain；没有则把 text/html 简单转文本。"""
    plain, html_body = "", ""
    for part in _walk_parts(payload):
        mime = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")
        if not data:
            continue
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if mime == "text/plain" and not plain:
            plain = decoded
        elif mime == "text/html" and not html_body:
            html_body = decoded

    if plain.strip():
        return plain.strip()
    if html_body.strip():
        # 极简 HTML 转纯文本：去标签 + 解 HTML 实体
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_body, flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</p>", "\n\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text).strip()
    return ""


def _extract_pdf_attachments(service, msg_id: str, payload: dict) -> list[tuple[str, bytes]]:
    """返回 [(filename, data_bytes), ...]，仅 .pdf。"""
    out: list[tuple[str, bytes]] = []
    for part in _walk_parts(payload):
        filename = part.get("filename", "") or ""
        if not filename.lower().endswith(".pdf"):
            continue
        body = part.get("body", {}) or {}
        data = body.get("data")
        if not data:
            att_id = body.get("attachmentId")
            if not att_id:
                continue
            att = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=att_id,
            ).execute()
            data = att.get("data")
        if not data:
            continue
        out.append((filename, base64.urlsafe_b64decode(data)))
    return out


_PDF_URL_RE = re.compile(
    r"""https?://[^\s<>"'`]+?\.pdf(?:\?[^\s<>"'`]*)?""",
    re.IGNORECASE,
)


def _extract_pdf_links_from_body(payload: dict) -> list[tuple[str, str]]:
    """从 text/plain 和 text/html 正文里抓 .pdf 直链。
    返回 [(filename, url), ...]，按 URL 去重。
    用于 esemtia 这类把"附件"渲染成正文链接的邮件（实际文件托管在 S3）。"""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for part in _walk_parts(payload):
        mime = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")
        if not data or mime not in ("text/plain", "text/html"):
            continue
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if mime == "text/html":
            decoded = html.unescape(decoded)
        for url in _PDF_URL_RE.findall(decoded):
            if url in seen:
                continue
            seen.add(url)
            fname = unquote(urlparse(url).path.rsplit("/", 1)[-1]) or "briefing.pdf"
            out.append((fname, url))
    return out


def _download_pdf(url: str, *, timeout_s: int = 30) -> tuple[str, bytes] | None:
    """GET 一个 PDF 直链，校验返回是 PDF（按 Content-Type 或文件头）。
    成功返回 (filename, bytes)，失败返回 None。"""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SchoolHelper/1.0)"},
            timeout=timeout_s, allow_redirects=True,
        )
    except requests.RequestException as e:
        logger.warning(f"下载 {url[:80]} 失败: {e}")
        return None
    if resp.status_code != 200:
        logger.warning(f"下载 {url[:80]} HTTP {resp.status_code}")
        return None
    ctype = (resp.headers.get("Content-Type", "") or "").lower()
    if "pdf" not in ctype and not resp.content[:4].startswith(b"%PDF"):
        logger.warning(f"{url[:80]} 不是 PDF (ctype={ctype})")
        return None
    fname = unquote(urlparse(url).path.rsplit("/", 1)[-1]) or "briefing.pdf"
    return fname, resp.content


# ---------- pipeline trigger ----------

def _safe_pdf_name(name: str) -> str:
    """防止异常字符进文件系统。"""
    base = Path(name).name
    base = re.sub(r"[^A-Za-z0-9._À-ɏ一-鿿-]", "_", base)
    return base or "briefing.pdf"


def _run_pipeline(input_dir: Path) -> tuple[bool, str]:
    """同步运行 main.py。返回 (成功, 末尾日志摘要)。"""
    env = os.environ.copy()
    env.setdefault("LANG", "en_US.UTF-8")
    cmd = [str(_HERE / ".venv" / "bin" / "python"), str(_HERE / "main.py")]
    if not Path(cmd[0]).exists():
        cmd[0] = sys.executable
    try:
        proc = subprocess.run(
            cmd, cwd=_HERE, env=env,
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, "main.py 运行超时（10 分钟）"
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-15:])
    return proc.returncode == 0, tail


def _git_publish(output_dir: Path, week_label: str) -> tuple[bool, str]:
    """在 output 仓库 add/commit/push。返回 (成功, 末尾日志)。"""
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=output_dir,
            capture_output=True, text=True, timeout=120,
        )

    # 先看有无变化
    status = run("status", "--porcelain")
    if status.returncode != 0:
        return False, f"git status 失败: {status.stderr.strip()}"
    if not status.stdout.strip():
        return True, "(无变化，跳过 push)"

    add = run("add", "-A")
    if add.returncode != 0:
        return False, f"git add 失败: {add.stderr.strip()}"

    msg = f"weekly: {week_label or 'briefing'} update {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    commit = run("commit", "-m", msg)
    if commit.returncode != 0 and "nothing to commit" not in commit.stdout.lower():
        return False, f"git commit 失败: {commit.stderr.strip() or commit.stdout.strip()}"

    push = run("push")
    if push.returncode != 0:
        return False, f"git push 失败: {push.stderr.strip()}"

    return True, push.stdout.strip() or "pushed"


def _translate_to_cn(body: str, subject: str, cfg: dict) -> str:
    """把邮件正文翻译成中文。失败时返回空串，不阻塞推送。"""
    try:
        from analyzer.llm_client import LLMClient
        llm = LLMClient(cfg)
    except Exception as e:
        logger.warning(f"LLM 初始化失败，跳过翻译: {e}")
        return ""

    system = (
        "你是西班牙学校发给中国家长的通知翻译助手。"
        "把邮件正文翻译成自然流畅的中文，**保留所有关键信息**——日期、时间、地点、"
        "家长/学生的具体动作、报名/缴费要求。"
        "**不要加任何解释、序言、结尾**，只输出中文译文，可以保留原文里的人名/学校名/项目名作西/英括注。"
    )
    user = (
        f"[邮件主题]\n{subject}\n\n"
        f"[邮件正文]\n{body[:6000]}"
    )
    try:
        return llm.complete(system, user).strip()
    except Exception as e:
        logger.warning(f"翻译调用失败: {e}")
        return ""


def _read_week_label(output_dir: Path) -> str:
    j = output_dir / "extracted_links.json"
    if not j.exists():
        return ""
    try:
        d = json.loads(j.read_text())
        return d.get("week_label") or d.get("week_iso") or ""
    except (json.JSONDecodeError, OSError):
        return ""


# ---------- core handler ----------

def handle_message(service, msg_id: str, cfg: dict, notifier: Notifier,
                   *, dry_run: bool = False) -> str:
    """处理一封邮件。返回简短结果描述（用于日志）。"""
    msg = _get_message(service, msg_id)
    payload = msg.get("payload", {}) or {}
    headers = payload.get("headers", []) or []
    subject = _header(headers, "Subject") or "(无主题)"
    sender_raw = _header(headers, "From") or ""
    _, sender_email = parseaddr(sender_raw)
    received_ts = int(msg.get("internalDate", 0)) // 1000
    received_iso = (
        datetime.fromtimestamp(received_ts, tz=timezone.utc).astimezone().isoformat(timespec="minutes")
        if received_ts else ""
    )

    # 1) MIME 附件
    pdfs = _extract_pdf_attachments(service, msg_id, payload)
    # 2) 正文里的 .pdf 直链（esemtia 用 S3 链接代替真附件）
    pdf_links = _extract_pdf_links_from_body(payload)

    if dry_run:
        link_summary = ", ".join(fn for fn, _ in pdf_links) or "无"
        return f"[dry-run] {subject!r} mime_pdfs={len(pdfs)} body_links={len(pdf_links)} ({link_summary})"

    # 把正文链接下载下来，合并到 pdfs
    for fname, url in pdf_links:
        result = _download_pdf(url)
        if result:
            pdfs.append(result)
            logger.info(f"从正文链接下载 PDF: {fname}")

    if pdfs:
        # 1) 保存附件到 input/
        input_dir = Path(cfg["paths"]["input_dir"])
        input_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for fname, data in pdfs:
            target = input_dir / _safe_pdf_name(fname)
            target.write_bytes(data)
            saved.append(target)
            logger.info(f"已保存附件: {target}")

        # 2) 跑 pipeline
        ok, tail = _run_pipeline(_HERE)
        if not ok:
            notifier.send(
                f"❌ *School Helper 失败*\n"
                f"邮件: `{subject}`\n时间: {received_iso}\n\n"
                f"```\n{tail[-1500:]}\n```"
            )
            return f"pipeline 失败: {tail[:120]}"

        # 3) git push
        output_dir = Path(cfg["paths"]["output_dir"])
        week_label = _read_week_label(output_dir)
        pushed, push_tail = _git_publish(output_dir, week_label)
        site_url = cfg.get("publish", {}).get("site_url", "")

        if pushed:
            lines = [
                "✅ *本周 Briefing 已更新*",
                f"邮件: `{subject}`",
                f"周次: {week_label or '(未知)'}",
                f"时间: {received_iso}",
                f"附件: {', '.join(p.name for p in saved)}",
            ]
            if site_url:
                lines += ["", f"🔗 {site_url}"]
            notifier.send("\n".join(lines))
            return f"published week={week_label}"
        else:
            notifier.send(
                f"⚠️ *Briefing 已生成但发布失败*\n"
                f"邮件: `{subject}`\n周次: {week_label or '(未知)'}\n\n"
                f"```\n{push_tail[-1500:]}\n```"
            )
            return f"git 失败: {push_tail[:120]}"

    # 无 PDF 附件：推送邮件正文 + 中文翻译
    body = _extract_body_text(payload)
    excerpt = body[:1200] + ("\n…(截断)" if len(body) > 1200 else "") if body else "(无正文)"
    translation = _translate_to_cn(body, subject, cfg) if body.strip() else ""

    parts = [
        "📧 学校来信（无附件）",
        f"主题: {subject}",
        f"发件人: {sender_email}",
        f"时间: {received_iso}",
        "",
        "— 西/英原文 —",
        excerpt,
    ]
    if translation:
        cn_excerpt = translation[:1200] + ("\n…(截断)" if len(translation) > 1200 else "")
        parts += ["", "— 中文翻译 —", cn_excerpt]
    # 邮件正文里随机字符可能撞 Markdown 语法，直接走纯文本最稳
    notifier.send("\n".join(parts), parse_mode=None)
    return f"forwarded body subject={subject!r}"


# ---------- main ----------

def main() -> int:
    p = argparse.ArgumentParser(description="周期性检测学校邮件并触发 pipeline")
    p.add_argument("--auth", action="store_true", help="只跑 OAuth 授权流程，不处理邮件")
    p.add_argument("--dry-run", action="store_true", help="只列出将处理的邮件，不真正运行 pipeline / 发 TG")
    p.add_argument("--force-msg-id", help="强制处理指定 message_id（忽略已处理状态）")
    args = p.parse_args()

    cfg = load_config()
    email_cfg = cfg.get("email", {}) or {}
    sender = email_cfg.get("sender", "comunicaciones@esemtia.com")
    lookback_days = int(email_cfg.get("lookback_days", 7))

    service = _get_gmail_service()
    if args.auth:
        logger.info("授权完成")
        return 0

    state = _load_state()
    processed: set[str] = set(state.get("processed_message_ids", []))

    if args.force_msg_id:
        ids = [args.force_msg_id]
        new_ids = ids  # --force 跳过已处理过滤
    else:
        ids = _list_messages(service, sender, lookback_days)
        new_ids = [i for i in ids if i not in processed]
    logger.info(f"扫描完成: 总计 {len(ids)} 封符合条件，新邮件 {len(new_ids)} 封")

    if not new_ids:
        return 0

    notifier = Notifier()

    for msg_id in new_ids:
        try:
            result = handle_message(service, msg_id, cfg, notifier, dry_run=args.dry_run)
            logger.info(f"[{msg_id}] {result}")
        except Exception as e:
            logger.exception(f"[{msg_id}] 处理失败: {e}")
            notifier.send(f"❌ *邮件处理异常*\nmsg_id=`{msg_id}`\n\n```\n{e}\n```")
            # 异常时不标记为已处理，下次再试
            continue
        if not args.dry_run:
            state.setdefault("processed_message_ids", []).append(msg_id)
            _save_state(state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
