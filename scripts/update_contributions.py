"""
Fetch Rich627's open-source PRs and update the README contributions table.

Usage:
  python scripts/update_contributions.py

Requires GITHUB_TOKEN env var (provided by GitHub Actions automatically).
"""

import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse

GITHUB_USER = "Rich627"
README_PATH = "README.md"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Repos to exclude (private, work-internal, test, or owned by self)
EXCLUDE_OWNERS = {GITHUB_USER.lower(), "rdot-lee"}
EXCLUDE_REPOS = {
    "iKala-SA-TAM-unofficial/viewsonic_webscale_tf_code",
    "iKala-SA-TAM-unofficial/viewsonic_caf_tf_code",
    "iKala-SA-TAM-unofficial/bedrock-claude-chat-old",
    "tmj-studio/tailormyjob_private",
    "punkpeye/awesome-mcp-servers",  # duplicate, closed
}

# Repos to always pin at top (in order), even if API misses them
PINNED = []


def github_api(url: str):
    """Call GitHub REST API with pagination."""
    items = []
    while url:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github+json")
        if TOKEN:
            req.add_header("Authorization", f"Bearer {TOKEN}")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            if isinstance(data, dict) and "items" in data:
                items.extend(data["items"])
            elif isinstance(data, list):
                items.extend(data)
            # pagination
            link = resp.headers.get("Link", "")
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split("<")[1].split(">")[0]
    return items


def fetch_prs():
    """Fetch all merged/open PRs by the user in external repos."""
    query = urllib.parse.quote(f"author:{GITHUB_USER} is:pr")
    url = (
        f"https://api.github.com/search/issues?q={query}"
        f"&sort=created&order=desc&per_page=100"
    )
    return github_api(url)


def build_contributions(prs):
    """Group PRs by repo and pick the best representation."""
    repo_map = {}  # repo_full_name -> {title, pr_number, pr_url, count, is_merged}

    for pr in prs:
        repo_url = pr.get("repository_url", "")
        repo_full = "/".join(repo_url.split("/")[-2:])
        owner = repo_url.split("/")[-2].lower()

        # Skip excluded
        if owner in EXCLUDE_OWNERS:
            continue
        if repo_full in EXCLUDE_REPOS:
            continue

        pr_number = pr["number"]
        pr_title = pr["title"]
        html_url = pr["html_url"]
        state = pr.get("state", "")
        is_merged = pr.get("pull_request", {}).get("merged_at") is not None

        if repo_full not in repo_map:
            repo_map[repo_full] = {
                "title": pr_title,
                "number": pr_number,
                "url": html_url,
                "count": 1,
                "is_merged": is_merged,
                "state": state,
            }
        else:
            repo_map[repo_full]["count"] += 1
            # Prefer merged PRs; among merged, prefer latest
            existing = repo_map[repo_full]
            if (is_merged and not existing["is_merged"]) or (
                is_merged == existing["is_merged"] and pr_number > existing["number"]
            ):
                existing.update(
                    title=pr_title,
                    number=pr_number,
                    url=html_url,
                    is_merged=is_merged,
                    state=state,
                )

    return repo_map


def format_table(repo_map):
    """Build the markdown table rows."""
    rows = []

    # Sort: merged first, then by PR count desc, then alphabetically
    def sort_key(item):
        name, info = item
        return (not info["is_merged"], -info["count"], name.lower())

    sorted_items = sorted(repo_map.items(), key=sort_key)[:5]  # Top 5 only

    for repo_full, info in sorted_items:
        count = info["count"]
        title = info["title"]

        if count > 3:
            contribution = f"{title} & more ({count} PRs)"
            prs_query = f"https://github.com/{repo_full}/pulls?q=is%3Apr+author%3A{GITHUB_USER}"
            link = f"[PRs]({prs_query})"
        else:
            contribution = f"`{title}`" if title.startswith(("feat", "fix", "chore", "refactor", "ci", "docs")) else title
            link = f"[PR #{info['number']}]({info['url']})"

        rows.append(f"| **{repo_full}** | {contribution} | {link} |")

    return rows


def update_readme(rows):
    """Replace the contributions table in README.md."""
    with open(README_PATH, "r") as f:
        content = f.read()

    header = "| Project | Contribution | Link |\n|---------|-------------|------|\n"

    # Find the existing table
    pattern = r"(\| Project \| Contribution \| Link \|\n\|[-| ]+\|\n)((?:\|.*\|\n?)*)"
    match = re.search(pattern, content)
    if not match:
        print("Could not find contributions table in README.md")
        return False

    new_table = header + "\n".join(rows) + "\n"
    new_content = content[: match.start()] + new_table + content[match.end() :]

    if new_content == content:
        print("No changes needed.")
        return False

    with open(README_PATH, "w") as f:
        f.write(new_content)

    print(f"Updated contributions table with {len(rows)} repos.")
    return True


def main():
    print(f"Fetching PRs for {GITHUB_USER}...")
    prs = fetch_prs()
    print(f"Found {len(prs)} PRs total.")

    repo_map = build_contributions(prs)
    print(f"Found {len(repo_map)} external repos.")

    rows = format_table(repo_map)
    updated = update_readme(rows)
    return 0 if updated or not updated else 1


if __name__ == "__main__":
    raise SystemExit(main())
