"""将 public/ 目录发布到 GitHub Pages。失败时保留本地文件，不影响主流程。"""

import os
import base64
from pathlib import Path
from github import Github, GithubException, InputGitTreeElement

from src.core import config
from src.core.logger import get_logger
from src.core.utils import today_str

log = get_logger(__name__)


def _get_client():
    token = os.getenv(config.get("github.token_env", "GITHUB_TOKEN"), "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 未配置")
    return Github(token)


def publish() -> bool:
    """上传 public/ 到 GitHub Pages 分支，返回是否成功。"""
    if not config.get("github.enabled"):
        log.info("[github] GitHub 发布已禁用，跳过")
        return False

    repo_name = config.get("github.repo", "")
    if not repo_name:
        log.warning("[github] github.repo 未配置，跳过发布")
        return False

    branch = config.get("github.branch", "main")
    pages_dir = config.get("github.pages_dir", "public")
    commit_msg = config.get("github.commit_message", "chore: update spain_assistant pages [{date}]")
    commit_msg = commit_msg.replace("{date}", today_str())

    public_path = config.root_dir / pages_dir

    try:
        gh = _get_client()
        repo = gh.get_repo(repo_name)

        ref = repo.get_git_ref(f"heads/{branch}")
        base_tree_sha = repo.get_git_commit(ref.object.sha).tree.sha

        # 构建文件 blobs，用 InputGitTreeElement（PyGithub 2.x 要求）
        elements = []
        for fpath in public_path.rglob("*"):
            if fpath.name.startswith("._") or fpath.name == ".gitkeep":
                continue
            try:
                if not fpath.is_file():
                    continue
            except OSError:
                continue
            rel = str(fpath.relative_to(public_path)).replace("\\", "/")
            content = fpath.read_bytes()
            blob = repo.create_git_blob(base64.b64encode(content).decode(), "base64")
            elements.append(InputGitTreeElement(path=rel, mode="100644", type="blob", sha=blob.sha))

        if not elements:
            log.warning("[github] public/ 无文件可上传")
            return False

        base_tree = repo.get_git_tree(base_tree_sha)
        tree = repo.create_git_tree(elements, base_tree=base_tree)
        parent_commit = repo.get_git_commit(ref.object.sha)
        new_commit = repo.create_git_commit(commit_msg, tree, [parent_commit])
        ref.edit(new_commit.sha, force=True)

        log.info(f"[github] 发布成功: {repo_name} branch={branch} files={len(elements)}")
        return True

    except GithubException as e:
        log.error(f"[github] GitHub API 错误: {e.status} {e.data}")
        return False
    except Exception as e:
        log.error(f"[github] 发布失败（本地文件保留）: {e}")
        return False
