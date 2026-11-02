#!/usr/bin/env python3
"""
OMEGA 5TB Cloud Storage Vault & Remote Mount Manager
----------------------------------------------------
1. Separates CRITICAL LOCAL RUNTIME files (which must stay in /root for 24/7 daemons)
   from ARCHIVAL / HEAVY PROJECT folders (which can live on 5TB Cloud Storage and be
   operated remotely via rclone mount / symlink / on-demand stream).
2. Builds a Zstandard-compressed Critical Vault Backup (/root/CLOUD_5TB_VAULT/omega_critical_vault.tar.zst)
   containing all wallets, private keys, tokens, and 24/7 daemon scripts.
3. Provides 1-command Cloud Sync, Remote Mount, and Safe Mobile Storage Cleaner.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

VAULT_DIR = "/root/CLOUD_5TB_VAULT"
CLOUD_MOUNT_DIR = "/root/cloud_5tb_mount"
MANIFEST_FILE = os.path.join(VAULT_DIR, "storage_partition_manifest.json")
CRITICAL_ARCHIVE = os.path.join(VAULT_DIR, "omega_critical_vault.tar.zst")

# 1. MUST STAY IN LOCAL TERMINAL (/root) FOR ZERO-ERROR 24/7 EXECUTION
ESSENTIAL_LOCAL_RUNTIME = [
    "/root/unified_24x7_agent_hub.py",
    "/root/colab_crypto_miner_daemon.py",
    "/root/colab_crypto_mining_state.json",
    "/root/agent_team.py",
    "/root/ai",
    "/root/agent.py",
    "/root/AGENTS.md",
    "/root/.agents",
    "/root/.gemini",
    "/root/venv",
    "/root/Colab-Crypto-Mining/libducohasher_fast.so",
    "/root/Colab-Crypto-Mining/xmrig_arm64",
    "/root/NerdMiner-Modded/libnerdsha256d.so",
    "/root/UG-Miner",
    "/root/wallets_export.json",
    "/root/wallets.html",
    "/root/mywallets",
    "/root/.near_github_wallet.json",
    "/root/near_to_github_wallet_transfer.py",
    "/root/send_near_to_github.sh",
    "/root/update_wallets_complete.py",
    "/root/.automaton",
    "/root/.halo_mini_tokens.json",
    "/root/.gitconfig",
    "/root/.ssh",
    "/root/pr_status.json",
]

# 2. HEAVY ARCHIVAL / RESEARCH REPOS TO MOVE TO 5TB CLOUD & OPERATE VIA REMOTE MOUNT / SYMLINK
CLOUD_5TB_OFFLOAD_CANDIDATES = [
    "/root/Rich-Address-Wallet",
    "/root/java-tron",
    "/root/btcd",
    "/root/btx",
    "/root/bounty-work",
    "/root/crypto-wallet-tools",
    "/root/reused-r-scanner",
    "/root/bitcoin-key-security-research",
    "/root/ecdsa-private-key-recovery",
    "/root/tron-multisig-vulnerability-poc",
    "/root/tron-wallet-suite",
    "/root/Carding-Tools-Web-V2",
    "/root/StripeChecker-V2",
    "/root/Gmail-Hack",
    "/root/Downloads",
    "/sdcard/Download",
    "/sdcard/MT2",
]


def ensure_dirs() -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    os.makedirs(CLOUD_MOUNT_DIR, exist_ok=True)


def build_critical_vault_bundle() -> dict:
    """Packs all critical keys, wallets, tokens, and 24/7 scripts into a fast zstd archive ready for 5TB Cloud."""
    ensure_dirs()
    bundle_items = [
        "/root/wallets_export.json",
        "/root/wallets.html",
        "/root/mywallets",
        "/root/.near_github_wallet.json",
        "/root/near_to_github_wallet_transfer.py",
        "/root/send_near_to_github.sh",
        "/root/update_wallets_complete.py",
        "/root/.automaton",
        "/root/.halo_mini_tokens.json",
        "/root/.gitconfig",
        "/root/.ssh",
        "/root/unified_24x7_agent_hub.py",
        "/root/colab_crypto_miner_daemon.py",
        "/root/colab_crypto_mining_state.json",
        "/root/agent_team.py",
        "/root/ai",
        "/root/AGENTS.md",
        "/root/.agents",
        "/root/pr_status.json",
    ]
    existing = [p for p in bundle_items if os.path.exists(p)]
    cmd = ["tar", "--zstd", "-cf", CRITICAL_ARCHIVE] + existing
    subprocess.run(cmd, check=False, stderr=subprocess.DEVNULL)
    size_mb = round(os.path.getsize(CRITICAL_ARCHIVE) / (1024 * 1024), 2) if os.path.exists(CRITICAL_ARCHIVE) else 0.0

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "critical_archive_path": CRITICAL_ARCHIVE,
        "critical_archive_size_mb": size_mb,
        "github_linked_wallets": {
            "github_user": "zainrizvi0611-cmd",
            "evm_eth_wallet": "0x0970e4ad9Ff0a9A183e9c22de4664CC4A17804e6",
            "btc_wallet_p2pkh": "1GAGs84f3byZJCwsqnUhvrrmxPQtkW97xq",
            "tron_wallet_base58": "TAq8KkKU7PTnPaww6zhPq2EVWNau1C55L2",
            "near_implicit_wallet": "7b41d8d0bedef30afe3edc164b0ddb85e5a93ed5bcf7b108b9e1499eb584f5eb",
        },
        "essential_local_runtime_files": ESSENTIAL_LOCAL_RUNTIME,
        "cloud_5tb_offload_candidates": CLOUD_5TB_OFFLOAD_CANDIDATES,
    }
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def offload_folder_to_cloud_and_symlink(folder_path: str, remote_target_base: str = CLOUD_MOUNT_DIR) -> dict:
    """
    Moves a heavy non-runtime folder to the mounted 5TB Cloud directory (or remote rclone target)
    and leaves a transparent symlink in /root so scripts can still operate on it seamlessly!
    """
    ensure_dirs()
    folder_path = os.path.abspath(folder_path)
    if not os.path.exists(folder_path) or os.path.islink(folder_path):
        return {"status": "SKIPPED", "path": folder_path, "reason": "Already symlinked or missing"}
    dest_path = os.path.join(remote_target_base, os.path.basename(folder_path))
    shutil.move(folder_path, dest_path)
    os.symlink(dest_path, folder_path)
    return {"status": "OFFLOADED_AND_SYMLINKED", "local_symlink": folder_path, "cloud_path": dest_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="OMEGA 5TB Cloud Vault & Mobile Storage Optimizer")
    parser.add_argument("--status", action="store_true", help="Show disk usage and partition manifest")
    parser.add_argument("--build-vault", action="store_true", help="Build compressed critical vault archive")
    parser.add_argument("--sync-remote", type=str, default="", help="rclone remote name (e.g. cloud5tb:omega_vault)")
    parser.add_argument("--offload", type=str, default="", help="Move a heavy folder to /root/cloud_5tb_mount and symlink it")
    args = parser.parse_args()

    manifest = build_critical_vault_bundle()
    if args.offload:
        res = offload_folder_to_cloud_and_symlink(args.offload)
        print(json.dumps(res, indent=2))
    if args.sync_remote:
        subprocess.run(["rclone", "copy", VAULT_DIR, args.sync_remote, "-P"], check=False)
    if args.status or not (args.offload or args.sync_remote):
        df_out = subprocess.check_output(["df", "-h", "/", "/sdcard"]).decode("utf-8", "ignore")
        print("=== DISK STATUS ===")
        print(df_out.strip())
        print("=== CRITICAL VAULT ARCHIVE BUILT ===")
        print(f"Archive: {manifest['critical_archive_path']} ({manifest['critical_archive_size_mb']} MB)")
        print(f"Manifest: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
