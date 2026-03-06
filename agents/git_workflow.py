#!/usr/bin/env python3
"""
Git Workflow — handles all git operations for the Guild system.

Branch creation, PR management, commit validation, and merge workflows.
"""

import logging
import re
import sqlite3
import subprocess
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)

GUILD_DIR = Path.home() / ".guild"
DB_PATH = GUILD_DIR / "guild.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _run_git(args, cwd):
    """Run a git command and return the CompletedProcess result.

    All git commands go through this helper so error handling is uniform.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result
    except Exception as exc:
        logger.error("Failed to run %s: %s", args, exc)
        return None


# ---------------------------------------------------------------------------
# 1. generate_branch_name
# ---------------------------------------------------------------------------

def generate_branch_name(quest_type, quest_id, title):
    """Generate a branch name from quest metadata.

    Format: {type}/GLD-{id}-{slug}
    Slug: lowercase, spaces to dashes, strip special chars, max 40 chars.
    Example: feature/GLD-ABC123-add-user-auth
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    slug = slug[:40].rstrip("-")

    return f"{quest_type}/GLD-{quest_id}-{slug}"


# ---------------------------------------------------------------------------
# 2. create_quest_branch
# ---------------------------------------------------------------------------

def create_quest_branch(project_path, branch_name, base_branch="development"):
    """Create a quest branch from a base branch.

    - Fetches from origin first.
    - Falls back to origin/main if base_branch doesn't exist remotely.
    - If branch already exists and matches the same quest prefix, reuses it.
    - If a different quest owns the branch name, appends -v2.
    - Returns the actual branch name used.
    """
    # Fetch latest
    result = _run_git(["git", "fetch", "origin"], cwd=project_path)
    if result is None:
        logger.error("git fetch failed for %s", project_path)
        return None

    # Check if branch already exists locally
    existing = _run_git(
        ["git", "branch", "--list", branch_name], cwd=project_path
    )
    if existing and existing.stdout.strip():
        # Branch exists locally — check if it belongs to the same quest
        # Extract quest prefix (e.g. "feature/GLD-ABC123")
        quest_prefix = "-".join(branch_name.split("-")[:2]) if "-" in branch_name else branch_name
        if existing.stdout.strip().startswith(quest_prefix.replace("* ", "")):
            # Same quest, reuse the branch
            _run_git(["git", "checkout", branch_name], cwd=project_path)
            logger.info("Reusing existing branch: %s", branch_name)
            return branch_name
        else:
            # Different quest — append -v2
            branch_name = branch_name + "-v2"
            logger.info("Branch conflict, using: %s", branch_name)

    # Also check remote branches
    remote_check = _run_git(
        ["git", "ls-remote", "--heads", "origin", branch_name], cwd=project_path
    )
    if remote_check and remote_check.stdout.strip():
        # Remote branch exists — check quest prefix match
        quest_prefix = "-".join(branch_name.split("-")[:2]) if "-" in branch_name else branch_name
        # Same name means same quest, just check it out
        checkout = _run_git(
            ["git", "checkout", "-b", branch_name, f"origin/{branch_name}"], cwd=project_path
        )
        if checkout and checkout.returncode == 0:
            logger.info("Checked out existing remote branch: %s", branch_name)
            return branch_name

    # Determine the actual base to branch from
    actual_base = base_branch
    base_check = _run_git(
        ["git", "ls-remote", "--heads", "origin", base_branch], cwd=project_path
    )
    if not base_check or not base_check.stdout.strip():
        logger.warning("Base branch '%s' not found on remote, falling back to main", base_branch)
        actual_base = "main"

    # Create the new branch
    result = _run_git(
        ["git", "checkout", "-b", branch_name, f"origin/{actual_base}"], cwd=project_path
    )
    if result is None or result.returncode != 0:
        stderr = result.stderr if result else "unknown error"
        logger.error("Failed to create branch %s: %s", branch_name, stderr)
        return None

    logger.info("Created branch %s from origin/%s", branch_name, actual_base)
    return branch_name


# ---------------------------------------------------------------------------
# 3. delete_merged_branch
# ---------------------------------------------------------------------------

def delete_merged_branch(project_path, branch_name):
    """Delete a merged branch locally and remotely (best-effort)."""
    # Delete local branch
    result = _run_git(["git", "branch", "-d", branch_name], cwd=project_path)
    if result is None or result.returncode != 0:
        stderr = result.stderr if result else "unknown error"
        logger.warning("Failed to delete local branch %s: %s", branch_name, stderr)
        return False

    # Delete remote branch (best-effort)
    remote_result = _run_git(
        ["git", "push", "origin", "--delete", branch_name], cwd=project_path
    )
    if remote_result is None or remote_result.returncode != 0:
        stderr = remote_result.stderr if remote_result else "unknown error"
        logger.warning("Failed to delete remote branch %s (best-effort): %s", branch_name, stderr)
        # Still return True since local deletion succeeded

    logger.info("Deleted branch %s", branch_name)
    return True


# ---------------------------------------------------------------------------
# 4. create_pr
# ---------------------------------------------------------------------------

def create_pr(project_path, branch_name, base_branch, title, body, provider):
    """Create a pull/merge request using the appropriate CLI tool.

    Supported providers: 'github', 'gitlab', 'none'.
    Returns the PR/MR URL or None.
    """
    if provider == "github":
        result = _run_git(
            [
                "gh", "pr", "create",
                "--base", base_branch,
                "--head", branch_name,
                "--title", title,
                "--body", body,
            ],
            cwd=project_path,
        )
        if result and result.returncode == 0:
            pr_url = result.stdout.strip()
            logger.info("Created GitHub PR: %s", pr_url)
            return pr_url
        else:
            stderr = result.stderr if result else "unknown error"
            logger.error("Failed to create GitHub PR: %s", stderr)
            return None

    elif provider == "gitlab":
        result = _run_git(
            [
                "glab", "mr", "create",
                "--source-branch", branch_name,
                "--target-branch", base_branch,
                "--title", title,
                "--description", body,
                "--no-editor",
            ],
            cwd=project_path,
        )
        if result and result.returncode == 0:
            # glab outputs the MR URL
            mr_url = result.stdout.strip()
            logger.info("Created GitLab MR: %s", mr_url)
            return mr_url
        else:
            stderr = result.stderr if result else "unknown error"
            logger.error("Failed to create GitLab MR: %s", stderr)
            return None

    elif provider == "none":
        logger.info(
            "No git provider configured. Manual merge required.\n"
            "  Branch: %s -> %s\n"
            "  Title: %s",
            branch_name, base_branch, title,
        )
        return None

    else:
        logger.error("Unknown git provider: %s", provider)
        return None


# ---------------------------------------------------------------------------
# 4b. create_merge_pr (dev -> main)
# ---------------------------------------------------------------------------

def create_merge_pr(project_path, dev_branch, main_branch, title, body):
    """Create a PR from dev_branch to main_branch.

    Detects the git provider from the project DB entry or falls back to
    trying GitHub CLI then GitLab CLI.
    Returns the PR/MR URL or None.
    """
    conn = get_db()
    project = conn.execute(
        "SELECT * FROM projects WHERE path = ?", (str(project_path),)
    ).fetchone()
    conn.close()

    provider = None
    if project and "git_provider" in project.keys():
        provider = project["git_provider"]

    if not provider:
        owner, repo = get_repo_info(project_path)
        if owner:
            provider = "github"
        else:
            provider = "none"

    return create_pr(project_path, dev_branch, main_branch, title, body, provider)


# ---------------------------------------------------------------------------
# 5. auto_create_quest_pr
# ---------------------------------------------------------------------------

def auto_create_quest_pr(conn, quest_id):
    """Automatically create a PR for a completed quest.

    Looks up quest, project, and chain info from the DB, builds a PR body
    with description, branch, changed files, and learnings, then creates
    the PR and stores the URL in the quest result field.

    Returns the PR URL or None.
    """
    quest = conn.execute("SELECT * FROM quests WHERE id = ?", (quest_id,)).fetchone()
    if not quest:
        logger.error("Quest %s not found", quest_id)
        return None

    project = conn.execute("SELECT * FROM projects WHERE id = ?", (quest["project_id"],)).fetchone()
    if not project:
        logger.error("Project not found for quest %s", quest_id)
        return None

    project_path = project["path"]
    provider = project["git_provider"] if "git_provider" in project.keys() else "none"
    base_branch = project["default_branch"] if "default_branch" in project.keys() else "development"
    branch_name = quest["branch"]

    # Build PR body
    body_parts = []
    body_parts.append(f"## Quest: {quest['title']}")
    body_parts.append(f"**ID:** {quest_id}")
    body_parts.append(f"**Tier:** {quest['tier']} | **Type:** {quest['type']}")
    body_parts.append(f"**Branch:** `{branch_name}`")
    body_parts.append("")

    # Description
    if quest["description"]:
        body_parts.append("### Description")
        body_parts.append(quest["description"])
        body_parts.append("")

    # Chain info
    if quest["chain_id"]:
        chain = conn.execute(
            "SELECT * FROM quest_chains WHERE id = ?", (quest["chain_id"],)
        ).fetchone()
        if chain:
            body_parts.append(f"### Quest Chain")
            body_parts.append(f"**Goal:** {chain['goal']}")
            body_parts.append("")

    # Changed files
    changed_files = get_changed_files(project_path, branch_name, base_branch)
    if changed_files:
        body_parts.append("### Changed Files")
        for f in changed_files:
            body_parts.append(f"- `{f}`")
        body_parts.append("")

    # Learnings from hero history
    if quest.get("assigned_to"):
        hero = conn.execute("SELECT name FROM heroes WHERE id = ?", (quest["assigned_to"],)).fetchone()
        if hero:
            hero_name = hero["name"]
            history_file = (
                GUILD_DIR / "workspace" / "memory" / "heroes" / hero_name / "history.md"
            )
            if history_file.exists():
                history = history_file.read_text()
                # Extract learnings for this quest
                pattern = rf"## {re.escape(quest_id)}.*?\n([\s\S]*?)(?=\n## |\Z)"
                match = re.search(pattern, history)
                if match:
                    learnings_text = match.group(1).strip()
                    if learnings_text:
                        body_parts.append("### Learnings")
                        body_parts.append(learnings_text)
                        body_parts.append("")

    body = "\n".join(body_parts)
    title = f"[{quest_id}] {quest['title']}"

    pr_url = create_pr(project_path, branch_name, base_branch, title, body, provider)

    # Store PR URL in quest result
    if pr_url:
        conn.execute("UPDATE quests SET result = ? WHERE id = ?", (pr_url, quest_id))
        conn.commit()
        logger.info("Stored PR URL for quest %s: %s", quest_id, pr_url)

    return pr_url


# ---------------------------------------------------------------------------
# 6. check_pr_status
# ---------------------------------------------------------------------------

def check_pr_status(project_path, pr_url, provider):
    """Check the status of a PR/MR.

    Returns one of: 'open', 'merged', 'approved', 'changes_requested', 'closed',
    or None on error.
    """
    if provider == "github":
        # Extract PR number from URL
        match = re.search(r"/pull/(\d+)", pr_url)
        if not match:
            logger.error("Could not extract PR number from URL: %s", pr_url)
            return None

        pr_number = match.group(1)
        result = _run_git(
            ["gh", "pr", "view", pr_number, "--json", "state,reviews"],
            cwd=project_path,
        )
        if result is None or result.returncode != 0:
            stderr = result.stderr if result else "unknown error"
            logger.error("Failed to check PR status: %s", stderr)
            return None

        try:
            import json
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse PR status JSON: %s", exc)
            return None

        state = data.get("state", "").upper()

        if state == "MERGED":
            return "merged"
        elif state == "CLOSED":
            return "closed"
        elif state == "OPEN":
            # Check reviews for approval or changes requested
            reviews = data.get("reviews", [])
            for review in reversed(reviews):
                review_state = review.get("state", "").upper()
                if review_state == "APPROVED":
                    return "approved"
                elif review_state == "CHANGES_REQUESTED":
                    return "changes_requested"
            return "open"
        else:
            return state.lower() if state else None

    elif provider == "gitlab":
        match = re.search(r"/merge_requests/(\d+)", pr_url)
        if not match:
            logger.error("Could not extract MR number from URL: %s", pr_url)
            return None

        mr_number = match.group(1)
        result = _run_git(
            ["glab", "mr", "view", mr_number, "--output", "json"],
            cwd=project_path,
        )
        if result is None or result.returncode != 0:
            stderr = result.stderr if result else "unknown error"
            logger.error("Failed to check MR status: %s", stderr)
            return None

        try:
            import json
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse MR status JSON: %s", exc)
            return None

        state = data.get("state", "").lower()
        if state == "merged":
            return "merged"
        elif state == "closed":
            return "closed"
        elif state == "opened":
            return "open"
        else:
            return state if state else None

    else:
        logger.warning("Cannot check PR status for provider: %s", provider)
        return None


# ---------------------------------------------------------------------------
# 7. merge_pr
# ---------------------------------------------------------------------------

def merge_pr(project_path, pr_url, provider):
    """Merge a PR/MR.

    Returns True on success, False on failure.
    """
    if provider == "github":
        match = re.search(r"/pull/(\d+)", pr_url)
        if not match:
            logger.error("Could not extract PR number from URL: %s", pr_url)
            return False

        pr_number = match.group(1)
        result = _run_git(
            ["gh", "pr", "merge", pr_number, "--merge"],
            cwd=project_path,
        )
        if result and result.returncode == 0:
            logger.info("Merged PR #%s", pr_number)
            return True
        else:
            stderr = result.stderr if result else "unknown error"
            logger.error("Failed to merge PR #%s: %s", pr_number, stderr)
            return False

    elif provider == "gitlab":
        match = re.search(r"/merge_requests/(\d+)", pr_url)
        if not match:
            logger.error("Could not extract MR number from URL: %s", pr_url)
            return False

        mr_number = match.group(1)
        result = _run_git(
            ["glab", "mr", "merge", mr_number, "--yes"],
            cwd=project_path,
        )
        if result and result.returncode == 0:
            logger.info("Merged MR !%s", mr_number)
            return True
        else:
            stderr = result.stderr if result else "unknown error"
            logger.error("Failed to merge MR !%s: %s", mr_number, stderr)
            return False

    else:
        logger.error("Cannot merge PR for provider: %s", provider)
        return False


# ---------------------------------------------------------------------------
# 8. validate_commit_messages
# ---------------------------------------------------------------------------

def validate_commit_messages(project_path, branch_name, base_branch):
    """Validate commit messages on a branch match the Guild format.

    Expected format: [GLD-{id}] {description} -- {hero}
    Returns a list of invalid commit message strings.
    """
    result = _run_git(
        ["git", "log", f"{base_branch}..{branch_name}", "--oneline"],
        cwd=project_path,
    )
    if result is None or result.returncode != 0:
        stderr = result.stderr if result else "unknown error"
        logger.error("Failed to get commit log: %s", stderr)
        return None

    pattern = re.compile(r"^\w+\s+\[GLD-\w+\]\s+.+\s+(\u2014|--)\s+\S+")
    invalid = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if not pattern.match(line):
            invalid.append(line)

    return invalid


# ---------------------------------------------------------------------------
# 9. get_changed_files
# ---------------------------------------------------------------------------

def get_changed_files(project_path, branch_name, base_branch):
    """Get list of files changed between base and branch.

    Returns a list of file paths, or None on error.
    """
    result = _run_git(
        ["git", "diff", "--name-only", f"{base_branch}..{branch_name}"],
        cwd=project_path,
    )
    if result is None or result.returncode != 0:
        stderr = result.stderr if result else "unknown error"
        logger.error("Failed to get changed files: %s", stderr)
        return None

    files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    return files


# ---------------------------------------------------------------------------
# 10. check_branch_exists
# ---------------------------------------------------------------------------

def check_branch_exists(project_path, branch_name):
    """Check if a branch exists locally or on the remote.

    Returns True if the branch exists anywhere, False otherwise.
    """
    # Check local
    local = _run_git(
        ["git", "branch", "--list", branch_name], cwd=project_path
    )
    if local and local.stdout.strip():
        return True

    # Check remote
    remote = _run_git(
        ["git", "ls-remote", "--heads", "origin", branch_name], cwd=project_path
    )
    if remote and remote.stdout.strip():
        return True

    return False


# ---------------------------------------------------------------------------
# 11. get_repo_info
# ---------------------------------------------------------------------------

def get_repo_info(project_path):
    """Get owner/repo from git remote.

    Parses the origin URL (HTTPS or SSH) and returns (owner, repo).
    Returns (None, None) if parsing fails.
    """
    result = _run_git(["git", "remote", "get-url", "origin"], cwd=project_path)
    if result is None or result.returncode != 0:
        logger.warning("Could not get remote URL for %s", project_path)
        return None, None
    url = result.stdout.strip()
    # Parse github.com/owner/repo or similar (works for HTTPS and SSH)
    match = re.search(r'[:/]([^/]+)/([^/.]+)', url)
    if match:
        return match.group(1), match.group(2)
    logger.warning("Could not parse owner/repo from remote URL: %s", url)
    return None, None


# ---------------------------------------------------------------------------
# 12. setup_branch_protection
# ---------------------------------------------------------------------------

def setup_branch_protection(project_path, provider, main_branch="main", dev_branch="development"):
    """Configure branch protection rules via provider API.

    Uses get_repo_info to dynamically resolve owner/repo.
    Returns True on success, False on failure.
    """
    owner, repo = get_repo_info(project_path)
    if not owner or not repo:
        logger.warning("Cannot setup branch protection: unable to determine owner/repo")
        return False

    if provider == "github":
        try:
            # main branch: require PR, require approvals, enforce admins
            result = _run_git(["gh", "api", "-X", "PUT",
                f"/repos/{owner}/{repo}/branches/{main_branch}/protection",
                "-f", "required_pull_request_reviews[required_approving_review_count]=1",
                "-f", "enforce_admins=true",
                "-f", "required_status_checks=null",
                "-f", "restrictions=null"], cwd=project_path)
            if result is None or result.returncode != 0:
                stderr = result.stderr if result else "unknown error"
                logger.warning("Failed to protect branch %s: %s", main_branch, stderr)
                return False

            # dev branch: require PR, but don't enforce admins
            result = _run_git(["gh", "api", "-X", "PUT",
                f"/repos/{owner}/{repo}/branches/{dev_branch}/protection",
                "-f", "required_pull_request_reviews[required_approving_review_count]=1",
                "-f", "enforce_admins=false",
                "-f", "required_status_checks=null",
                "-f", "restrictions=null"], cwd=project_path)
            if result is None or result.returncode != 0:
                stderr = result.stderr if result else "unknown error"
                logger.warning("Failed to protect branch %s: %s", dev_branch, stderr)
                return False

            logger.info("Branch protection configured for %s/%s (github)", owner, repo)
            return True

        except Exception as exc:
            logger.warning("Branch protection setup failed: %s", exc)
            return False

    elif provider == "gitlab":
        try:
            # URL-encode owner/repo for GitLab project ID
            project_id = urllib.parse.quote(f"{owner}/{repo}", safe="")
            result = _run_git(["glab", "api", "-X", "POST",
                f"/projects/{project_id}/protected_branches",
                "-f", f"name={main_branch}",
                "-f", "push_access_level=0",
                "-f", "merge_access_level=40"], cwd=project_path)
            if result is None or result.returncode != 0:
                stderr = result.stderr if result else "unknown error"
                logger.warning("Failed to protect branch %s on GitLab: %s", main_branch, stderr)
                return False

            logger.info("Branch protection configured for %s/%s (gitlab)", owner, repo)
            return True

        except Exception as exc:
            logger.warning("GitLab branch protection setup failed: %s", exc)
            return False

    else:
        logger.warning("Branch protection not supported for provider: %s", provider)
        return False
