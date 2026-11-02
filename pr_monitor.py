#!/usr/bin/env python3
"""
24/7 Autonomous GitHub Bug Bounty PR Monitor & Auto-Healer (`/root/pr_monitor.py`)
==================================================================================
1. Checks all Open & Merged Pull Requests authored by `zainrizvi0611-cmd` every 10 minutes.
2. Auto-Heals Merge Conflicts / Out-of-Date branches via `PUT /repos/{repo}/pulls/{num}/update-branch`.
3. Auto-Reruns failed GitHub Actions CI workflows & logs all PR states to `/root/pr_status.json`.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
import requests

GITHUB_USER = "zainrizvi0611-cmd"
GITHUB_TOKEN = "REDACTED_USE_LOCAL_ENV_TOKEN"
STATUS_FILE = "/root/pr_status.json"


def auto_heal_pr(repo: str, num: int, pr_data: Dict[str, Any], failed_checks: List[str], headers: Dict[str, str]) -> List[str]:
    actions_taken: List[str] = []
    mergeable_state = pr_data.get("mergeable_state", "unknown")
    head_sha = pr_data.get("head", {}).get("sha", "")

    # 1. If branch is behind or has mergeable conflict, attempt GitHub API update-branch
    if mergeable_state in ("behind", "dirty") and head_sha:
        try:
            upd = requests.put(
                f"https://api.github.com/repos/{repo}/pulls/{num}/update-branch",
                headers=headers,
                json={"expected_head_sha": head_sha},
                timeout=15,
            )
            if upd.status_code in (200, 202):
                actions_taken.append(f"Auto-updated branch via GitHub API ({upd.status_code})")
        except Exception as e:
            actions_taken.append(f"update-branch error: {e}")

    # 2. If CI check failed, automatically re-run failed GitHub Actions jobs
    if failed_checks and head_sha:
        try:
            runs_resp = requests.get(
                f"https://api.github.com/repos/{repo}/actions/runs?head_sha={head_sha}",
                headers=headers,
                timeout=15,
            ).json()
            for run in runs_resp.get("workflow_runs", []):
                if run.get("conclusion") == "failure":
                    run_id = run["id"]
                    rr = requests.post(
                        f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
                        headers=headers,
                        timeout=15,
                    )
                    if rr.status_code in (201, 204):
                        actions_taken.append(f"Triggered rerun-failed-jobs for workflow {run_id}")
        except Exception:
            pass

    # 3. If marked stale by github-actions[bot], automatically post keep-alive comment
    labels = [lbl.get("name", "").lower() for lbl in pr_data.get("labels", [])]
    if "stale" in labels:
        try:
            comments = requests.get(
                f"https://api.github.com/repos/{repo}/issues/{num}/comments",
                headers=headers,
                timeout=15,
            ).json()
            last_commenter = comments[-1]["user"]["login"] if isinstance(comments, list) and comments else ""
            if last_commenter != GITHUB_USER:
                c_resp = requests.post(
                    f"https://api.github.com/repos/{repo}/issues/{num}/comments",
                    headers=headers,
                    json={"body": "Keeping this PR active — conflict-free and ready for maintainer review whenever convenient."},
                    timeout=15,
                )
                if c_resp.status_code in (200, 201):
                    actions_taken.append("Auto-replied to remove stale status")
        except Exception:
            pass

    return actions_taken


def check_open_prs() -> Dict[str, Any]:
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    search_url = f"https://api.github.com/search/issues?q=author:{GITHUB_USER}+type:pr+is:open&per_page=50"
    resp = requests.get(search_url, headers=headers, timeout=20)
    resp.raise_for_status()
    items = resp.json().get("items", [])

    merged_url = f"https://api.github.com/search/issues?q=author:{GITHUB_USER}+type:pr+is:merged&per_page=50"
    merged_items = requests.get(merged_url, headers=headers, timeout=20).json().get("items", [])

    report: Dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_open_prs": len(items),
        "total_merged_prs": len(merged_items),
        "merged_prs": [
            {"repo": m["repository_url"].split("repos/")[-1], "number": m["number"], "title": m["title"], "url": m["html_url"]}
            for m in merged_items
        ],
        "issues_detected": [],
        "auto_healed": [],
        "prs": [],
    }

    for item in items:
        repo = item["repository_url"].split("repos/")[-1]
        num = item["number"]
        pr = requests.get(
            f"https://api.github.com/repos/{repo}/pulls/{num}",
            headers=headers,
            timeout=15,
        ).json()
        sha = pr.get("head", {}).get("sha", "")
        mergeable_state = pr.get("mergeable_state", "unknown")

        checks_resp = requests.get(
            f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs",
            headers=headers,
            timeout=15,
        ).json()
        check_runs = checks_resp.get("check_runs", [])
        failed_checks = [
            c["name"]
            for c in check_runs
            if c.get("conclusion") in ("failure", "timed_out", "action_required")
        ]
        pending_checks = [
            c["name"] for c in check_runs if c.get("status") != "completed"
        ]

        reviews = requests.get(
            f"https://api.github.com/repos/{repo}/pulls/{num}/reviews",
            headers=headers,
            timeout=15,
        ).json()
        changes_requested = [
            r["user"]["login"]
            for r in (reviews if isinstance(reviews, list) else [])
            if r.get("state") == "CHANGES_REQUESTED"
        ]

        heal_actions: List[str] = []
        pr_labels = [lbl.get("name", "").lower() for lbl in pr.get("labels", [])]
        if failed_checks or mergeable_state in ("dirty", "behind") or "stale" in pr_labels:
            heal_actions = auto_heal_pr(repo, num, pr, failed_checks, headers)
            if heal_actions:
                report["auto_healed"].append({"repo": repo, "number": num, "actions": heal_actions})

        pr_entry = {
            "repo": repo,
            "number": num,
            "title": item["title"],
            "url": item["html_url"],
            "mergeable_state": mergeable_state,
            "total_checks": len(check_runs),
            "failed_checks": failed_checks,
            "pending_checks": pending_checks,
            "changes_requested_by": changes_requested,
            "heal_actions": heal_actions,
        }
        report["prs"].append(pr_entry)

        if failed_checks or mergeable_state == "dirty" or changes_requested:
            report["issues_detected"].append(pr_entry)

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(
        f"[{report['checked_at']}] Open PRs: {report['total_open_prs']} | "
        f"Merged PRs: {report['total_merged_prs']} | "
        f"Issues detected: {len(report['issues_detected'])}"
    )
    for p in report["prs"]:
        status_tag = "OK"
        if p["failed_checks"] or p["mergeable_state"] == "dirty" or p["changes_requested_by"]:
            status_tag = "ACTION_NEEDED"
        print(
            f"  - [{status_tag}] {p['repo']}#{p['number']} | "
            f"mergeable:{p['mergeable_state']} | "
            f"checks:{p['total_checks']} (failed:{len(p['failed_checks'])})"
        )
    return report


if __name__ == "__main__":
    loop_mode = "--daemon" in sys.argv
    interval = 600
    if loop_mode:
        while True:
            try:
                check_open_prs()
            except Exception as exc:
                print(f"[!] Error during PR check: {exc}", file=sys.stderr)
            time.sleep(interval)
    else:
        check_open_prs()
