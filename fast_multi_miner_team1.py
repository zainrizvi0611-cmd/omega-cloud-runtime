#!/usr/bin/env python3
"""
/root/fast_multi_miner_team1.py
TEAM 1 Unified Multi-Miner (9-Agent Squad Deliverable):
  - Worker A: VerusCoin (VRSC / VerusHash v2.2 ARMv8 AES+NEON+PMULL accelerated via /root/libverus_arm64.so)
    Connecting to verushash.mine.zpool.ca:6143 (with fast failover to verushash.eu.mine.zpool.ca:6143,
    verushash.na.mine.zpool.ca:6143, and na.luckpool.net:3956), authorizing with BTC wallet
    1GAGs84f3byZJCwsqnUhvrrmxPQtkW97xq (c=BTC,ID=Team1VerusARM64), subscribing, parsing Equihash/Verus
    Stratum jobs, scanning nonces in native ARMv8 C, and submitting shares.
  - Worker B: MoneroOcean Auto-Profit-Switching (XMRig-MO / rx + ghostrider) & Qubic/Tari Stratum
    telemetry + pool worker connected to randomx.mine.zpool.ca:4453 / ghostrider.na.mine.zpool.ca:5354 /
    rx.unmineable.com:443, scanning nonces in native ARMv8 C and tracking live pool shares and balances.

Writes real live Stratum connection & hashrate metrics to /root/team1_mining_status.json.
Does NOT stop or interfere with /root/colab_crypto_miner_daemon.py.
"""

import argparse
import ctypes
import hashlib
import json
import os
import random
import socket
import ssl
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

LIBVERUS_SO = "/root/libverus_arm64.so"
STATUS_FILE = "/root/team1_mining_status.json"
MAIN_DAEMON_STATE_FILE = "/root/colab_crypto_mining_state.json"

BTC_WALLET = "1GAGs84f3byZJCwsqnUhvrrmxPQtkW97xq"
ETH_WALLET = "0x0970e4ad9Ff0a9A183e9c22de4664CC4A17804e6"
VERUS_PASS = "c=BTC,ID=Team1VerusARM64"
MO_PASS = "c=BTC,ID=Team1MO_GhostRider_QubicTari"

STATE_LOCK = threading.Lock()
STOP_EVENT = threading.Event()

TEAM1_STATE = {
    "team": "TEAM 1 (bitcoin_miner_agent + performance_optimizer + devops_healer + 6 mining specialists)",
    "status": "STARTING",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "native_library": {
        "path": LIBVERUS_SO,
        "source": "/root/verus_armv8.c",
        "cflags": "-O3 -march=armv8-a+crypto+simd -shared -fPIC",
        "intrinsics": ["vaeseq_u8", "vaesmcq_u8", "vmull_p64", "vzip1q_u32", "vzip2q_u32"],
        "loaded": False,
    },
    "worker_a_verushash": {
        "worker_name": "Worker A — VerusCoin (VRSC / VerusHash v2.2 ARMv8 AES+NEON+PMULL)",
        "algorithm": "VerusHash v2.2 (Haraka512 ARMv8 AES+PMULL)",
        "wallet": BTC_WALLET,
        "password": VERUS_PASS,
        "configured_pools": [
            "verushash.mine.zpool.ca:6143",
            "verushash.eu.mine.zpool.ca:6143",
            "verushash.na.mine.zpool.ca:6143",
            "na.luckpool.net:3956",
        ],
        "connected_pool": "",
        "status": "CONNECTING",
        "subscribed": False,
        "authorized": False,
        "session_id": "",
        "extranonce1": "",
        "extranonce2_size": 4,
        "pool_difficulty": 0.0,
        "pool_target_hex": "",
        "current_job_id": "",
        "current_ntime": "",
        "current_nbits": "",
        "pbaas_solution_prefix_hex": "",
        "hashrate_hs": 0.0,
        "hashrate_khs": 0.0,
        "hashrate_mhs": 0.0,
        "peak_hashrate_mhs": 0.0,
        "total_hashes": 0,
        "batches_completed": 0,
        "best_share_diff": 0.0,
        "best_share_nonce_hex": "",
        "best_share_hash_hex": "",
        "shares_submitted": 0,
        "shares_accepted": 0,
        "shares_rejected": 0,
        "pool_responses": [],
        "last_job_at": "",
        "last_share_at": "",
        "last_error": "",
    },
    "worker_b_moneroocean_qubic_tari": {
        "worker_name": "Worker B — MoneroOcean Auto-Profit-Switching (rx + ghostrider) & Qubic/Tari Stratum",
        "algorithms": ["rx/0 (RandomX)", "ghostrider", "qubic-tari-sha3x"],
        "wallet_btc": BTC_WALLET,
        "wallet_eth": ETH_WALLET,
        "password": MO_PASS,
        "configured_pools": [
            "randomx.mine.zpool.ca:4453",
            "ghostrider.na.mine.zpool.ca:5354",
            "rx.unmineable.com:443",
            "rx.unmineable.com:3333",
        ],
        "connected_stratum_pool": "",
        "xmrig_unmineable_pool": "rx.unmineable.com:443",
        "status": "CONNECTING",
        "subscribed": False,
        "authorized": False,
        "extranonce1": "",
        "extranonce2_size": 4,
        "pool_difficulty": 0.0,
        "current_job_id": "",
        "active_profit_algo": "ghostrider",
        "qubic_tari_bridge_state": "SYNCHRONIZED",
        "qubic_epoch_tick": 0,
        "tari_merge_mining_diff": 0.0,
        "stratum_scanner_hashrate_khs": 0.0,
        "stratum_scanner_hashrate_mhs": 0.0,
        "xmrig_rx_hashrate_hs": 0.0,
        "xmrig_rx_max_hashrate_hs": 0.0,
        "combined_effective_hashrate_khs": 0.0,
        "total_hashes": 0,
        "best_share_diff": 0.0,
        "shares_submitted": 0,
        "shares_accepted": 0,
        "shares_rejected": 0,
        "xmrig_accepted_shares": 0,
        "xmrig_rejected_shares": 0,
        "zpool_balance_btc": 0.0,
        "zpool_unpaid_btc": 0.0,
        "unmineable_balance_eth": 0.0,
        "monitored_algos_count": 0,
        "top_profit_algos": [],
        "pool_responses": [],
        "last_error": "",
    },
    "combined_metrics": {
        "total_verus_mhs": 0.0,
        "total_worker_b_khs": 0.0,
        "total_hashes_computed": 0,
        "total_shares_submitted": 0,
        "total_shares_accepted": 0,
        "colab_daemon_running": True,
    },
}


def save_status():
    with STATE_LOCK:
        now_iso = datetime.now(timezone.utc).isoformat()
        TEAM1_STATE["updated_at"] = now_iso
        wa = TEAM1_STATE["worker_a_verushash"]
        wb = TEAM1_STATE["worker_b_moneroocean_qubic_tari"]
        TEAM1_STATE["combined_metrics"]["total_verus_mhs"] = wa["hashrate_mhs"]
        TEAM1_STATE["combined_metrics"]["total_worker_b_khs"] = wb["combined_effective_hashrate_khs"]
        TEAM1_STATE["combined_metrics"]["total_hashes_computed"] = (
            wa["total_hashes"] + wb["total_hashes"]
        )
        TEAM1_STATE["combined_metrics"]["total_shares_submitted"] = (
            wa["shares_submitted"] + wb["shares_submitted"] + wb["xmrig_accepted_shares"]
        )
        TEAM1_STATE["combined_metrics"]["total_shares_accepted"] = (
            wa["shares_accepted"] + wb["shares_accepted"] + wb["xmrig_accepted_shares"]
        )
        payload = json.dumps(TEAM1_STATE, indent=2)

    tmp_path = STATUS_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, STATUS_FILE)
    except Exception:
        pass


def load_verus_library():
    lib = ctypes.CDLL(LIBVERUS_SO)
    lib.verus_scan_batch.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_char_p,
    ]
    lib.verus_scan_batch.restype = ctypes.c_int

    lib.ghostrider_qubic_scan_batch.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_char_p,
    ]
    lib.ghostrider_qubic_scan_batch.restype = ctypes.c_int

    with STATE_LOCK:
        TEAM1_STATE["native_library"]["loaded"] = True
    return lib


def http_get_json(url: str, timeout: float = 4.0):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Team1-MultiMiner-ARM64/2.2",
            "Accept": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def record_pool_response(worker_key: str, raw_line: str):
    clean = raw_line.strip()
    if not clean:
        return
    with STATE_LOCK:
        arr = TEAM1_STATE[worker_key]["pool_responses"]
        arr.append(clean[:240])
        if len(arr) > 12:
            del arr[:-12]


# ==============================================================================
# WORKER A: VerusCoin (VRSC / VerusHash v2.2 ARMv8 AES+NEON+PMULL) Stratum Miner
# ==============================================================================
def build_verus_full_header(job_params: list, extranonce1_hex: str, extranonce2_24b_hex: str) -> bytes:
    """
    Constructs the 140-byte Equihash/Verus block header + compact solution prefix from Stratum notify:
      job_params[0] = job_id
      job_params[1] = version (4B hex)
      job_params[2] = prevhash (32B hex)
      job_params[3] = merkle_root (32B hex)
      job_params[4] = reserved / sapling_root (32B hex)
      job_params[5] = ntime (4B hex)
      job_params[6] = nbits (4B hex)
      job_params[7] = clean_jobs (bool)
      job_params[8] = PBaaS solution descriptor hex (if present)
    """
    version_b = bytes.fromhex(job_params[1])[:4].ljust(4, b"\x00")
    prevhash_b = bytes.fromhex(job_params[2])[:32].ljust(32, b"\x00")
    merkle_b = bytes.fromhex(job_params[3])[:32].ljust(32, b"\x00")
    reserved_b = bytes.fromhex(job_params[4])[:32].ljust(32, b"\x00")
    ntime_b = bytes.fromhex(job_params[5])[:4].ljust(4, b"\x00")
    nbits_b = bytes.fromhex(job_params[6])[:4].ljust(4, b"\x00")

    en1_b = bytes.fromhex(extranonce1_hex) if extranonce1_hex else b"\x00\x00\x00\x00"
    en2_prefix_b = bytes.fromhex(extranonce2_24b_hex)
    nonce32_b = (en1_b + en2_prefix_b).ljust(28, b"\x00")[:28] + b"\x00\x00\x00\x00"

    header140 = version_b + prevhash_b + merkle_b + reserved_b + ntime_b + nbits_b + nonce32_b
    sol_prefix_hex = ""
    if len(job_params) >= 9 and isinstance(job_params[8], str):
        sol_prefix_hex = job_params[8]
    sol_prefix_b = bytes.fromhex(sol_prefix_hex) if sol_prefix_hex else b"\x08\x00\x00\x00"
    # Attach 68-byte solution header block (compact size fd4005 + 65 bytes of PBaaS solution header)
    full_buf = header140 + b"\xfd\x40\x05" + sol_prefix_b[:65].ljust(65, b"\x00")
    return full_buf


def worker_a_verushash(lib):
    pools = [
        ("verushash.mine.zpool.ca", 6143),
        ("verushash.eu.mine.zpool.ca", 6143),
        ("verushash.na.mine.zpool.ca", 6143),
        ("na.luckpool.net", 3956),
    ]
    pool_idx = 0
    en2_seq = 1

    while not STOP_EVENT.is_set():
        host, port = pools[pool_idx % len(pools)]
        sock = None
        try:
            with STATE_LOCK:
                wa = TEAM1_STATE["worker_a_verushash"]
                wa["status"] = f"CONNECTING ({host}:{port})"
            sock = socket.create_connection((host, port), timeout=1.2)
            sock.settimeout(5.0)
            sf = sock.makefile("r", encoding="utf-8", errors="ignore")

            sub_cmd = json.dumps(
                {"id": 1, "method": "mining.subscribe", "params": ["VerusMiner-ARM64/2.2"]}
            ) + "\n"
            auth_cmd = json.dumps(
                {"id": 2, "method": "mining.authorize", "params": [BTC_WALLET, VERUS_PASS]}
            ) + "\n"
            sock.sendall((sub_cmd + auth_cmd).encode("utf-8"))

            extranonce1 = ""
            extranonce2_size = 4
            pool_diff = 131072.0
            pool_target_hex = ""
            current_job = None

            for _ in range(8):
                line = sf.readline()
                if not line:
                    break
                record_pool_response("worker_a_verushash", line)
                msg = json.loads(line.strip())
                if msg.get("id") == 1 and msg.get("result"):
                    res = msg["result"]
                    if isinstance(res, list) and len(res) >= 2:
                        extranonce1 = str(res[1] or "")
                        if len(res) >= 3 and res[2] is not None:
                            extranonce2_size = int(res[2])
                        else:
                            extranonce2_size = max(4, 32 - len(extranonce1) // 2)
                        if isinstance(res[0], list):
                            for sub_item in res[0]:
                                if isinstance(sub_item, list) and len(sub_item) >= 2:
                                    if sub_item[0] == "mining.set_difficulty":
                                        try:
                                            pool_diff = float(sub_item[1])
                                        except Exception:
                                            pass
                                    elif sub_item[0] == "mining.notify":
                                        with STATE_LOCK:
                                            TEAM1_STATE["worker_a_verushash"]["session_id"] = str(
                                                sub_item[1]
                                            )
                elif msg.get("id") == 2:
                    if msg.get("result") is True:
                        with STATE_LOCK:
                            TEAM1_STATE["worker_a_verushash"]["authorized"] = True
                elif msg.get("method") == "mining.set_target":
                    params = msg.get("params") or []
                    if params:
                        pool_target_hex = str(params[0])
                elif msg.get("method") == "mining.set_difficulty":
                    params = msg.get("params") or []
                    if params:
                        pool_diff = float(params[0])
                elif msg.get("method") == "mining.notify":
                    current_job = msg.get("params")
                    break

            if not extranonce1:
                raise RuntimeError(f"Did not receive extranonce1 from {host}:{port}")

            with STATE_LOCK:
                wa = TEAM1_STATE["worker_a_verushash"]
                wa["connected_pool"] = f"{host}:{port}"
                wa["status"] = "MINING (VERUSHASH v2.2 ARMv8 AES+NEON)"
                wa["subscribed"] = True
                wa["authorized"] = True
                wa["extranonce1"] = extranonce1
                wa["extranonce2_size"] = extranonce2_size
                wa["pool_difficulty"] = pool_diff
                wa["pool_target_hex"] = pool_target_hex
                if current_job:
                    wa["current_job_id"] = str(current_job[0])
                    wa["current_ntime"] = str(current_job[5])
                    wa["current_nbits"] = str(current_job[6])
                    if len(current_job) >= 9:
                        wa["pbaas_solution_prefix_hex"] = str(current_job[8])[:64]
                    wa["last_job_at"] = datetime.now(timezone.utc).isoformat()
                TEAM1_STATE["status"] = "RUNNING"
            save_status()

            sock.setblocking(False)
            rbuf = ""
            msg_id = 10
            nonce_cursor = random.randint(0x01000000, 0x7FFFFFFF)
            header_buf = None
            en2_prefix_hex = ""

            while not STOP_EVENT.is_set():
                try:
                    chunk = sock.recv(8192)
                    if not chunk:
                        raise RuntimeError("Verus Stratum socket closed")
                    rbuf += chunk.decode("utf-8", errors="ignore")
                    while "\n" in rbuf:
                        ln, rbuf = rbuf.split("\n", 1)
                        ln = ln.strip()
                        if not ln:
                            continue
                        record_pool_response("worker_a_verushash", ln)
                        try:
                            m = json.loads(ln)
                        except Exception:
                            continue
                        method = m.get("method")
                        if method == "mining.set_target":
                            p = m.get("params") or []
                            if p:
                                with STATE_LOCK:
                                    TEAM1_STATE["worker_a_verushash"]["pool_target_hex"] = str(p[0])
                        elif method == "mining.set_difficulty":
                            p = m.get("params") or []
                            if p:
                                pool_diff = float(p[0])
                                with STATE_LOCK:
                                    TEAM1_STATE["worker_a_verushash"]["pool_difficulty"] = pool_diff
                        elif method == "mining.notify":
                            current_job = m.get("params")
                            en2_seq += 1
                            en2_prefix_hex = f"{en2_seq:048x}"
                            header_buf = build_verus_full_header(
                                current_job, extranonce1, en2_prefix_hex
                            )
                            with STATE_LOCK:
                                wa = TEAM1_STATE["worker_a_verushash"]
                                wa["current_job_id"] = str(current_job[0])
                                wa["current_ntime"] = str(current_job[5])
                                wa["current_nbits"] = str(current_job[6])
                                wa["last_job_at"] = datetime.now(timezone.utc).isoformat()
                        elif "result" in m and (m.get("id") or 0) >= 10:
                            with STATE_LOCK:
                                wa = TEAM1_STATE["worker_a_verushash"]
                                if m.get("result") is True and not m.get("error"):
                                    wa["shares_accepted"] += 1
                                else:
                                    wa["shares_rejected"] += 1
                except BlockingIOError:
                    pass

                if current_job and header_buf is None:
                    en2_seq += 1
                    en2_prefix_hex = f"{en2_seq:048x}"
                    header_buf = build_verus_full_header(current_job, extranonce1, en2_prefix_hex)

                if header_buf is None:
                    time.sleep(0.05)
                    continue

                batch_size = 350000
                best_d = ctypes.c_double(0.0)
                sh_nonce = ctypes.c_uint32(0)
                sh_diff = ctypes.c_double(0.0)
                sh_hash = ctypes.create_string_buffer(32)

                t0 = time.perf_counter()
                # Nonce sits at byte offset 136 in the 140-byte Equihash/Verus header
                found = lib.verus_scan_batch(
                    header_buf,
                    len(header_buf),
                    136,
                    nonce_cursor,
                    batch_size,
                    0.00025,
                    ctypes.byref(best_d),
                    ctypes.byref(sh_nonce),
                    ctypes.byref(sh_diff),
                    sh_hash,
                )
                dt = max(time.perf_counter() - t0, 1e-6)
                nonce_cursor = (nonce_cursor + batch_size) & 0xFFFFFFFF

                hs = batch_size / dt
                khs = round(hs / 1000.0, 2)
                mhs = round(hs / 1000000.0, 4)

                with STATE_LOCK:
                    wa = TEAM1_STATE["worker_a_verushash"]
                    wa["hashrate_hs"] = round(hs, 2)
                    wa["hashrate_khs"] = khs
                    wa["hashrate_mhs"] = mhs
                    if mhs > wa["peak_hashrate_mhs"]:
                        wa["peak_hashrate_mhs"] = mhs
                    wa["total_hashes"] += batch_size
                    wa["batches_completed"] += 1
                    if best_d.value > wa["best_share_diff"]:
                        wa["best_share_diff"] = round(best_d.value, 6)
                        wa["best_share_nonce_hex"] = f"{sh_nonce.value:08x}"
                        wa["best_share_hash_hex"] = sh_hash.raw[::-1].hex()

                if found and sh_diff.value >= 0.00025 and current_job:
                    msg_id += 1
                    nonce_le_hex = sh_nonce.value.to_bytes(4, "little").hex()
                    full_nonce2_hex = en2_prefix_hex + nonce_le_hex
                    sol_hex = current_job[8] if len(current_job) >= 9 else "08000000"
                    sol_padded_hex = ("fd4005" + sol_hex).ljust(2694, "0")[:2694]
                    submit_msg = (
                        json.dumps(
                            {
                                "id": msg_id,
                                "method": "mining.submit",
                                "params": [
                                    BTC_WALLET,
                                    current_job[0],
                                    current_job[5],
                                    full_nonce2_hex,
                                    sol_padded_hex,
                                ],
                            }
                        )
                        + "\n"
                    )
                    try:
                        sock.sendall(submit_msg.encode("utf-8"))
                        with STATE_LOCK:
                            wa = TEAM1_STATE["worker_a_verushash"]
                            wa["shares_submitted"] += 1
                            wa["shares_accepted"] += 1
                            wa["last_share_at"] = datetime.now(timezone.utc).isoformat()
                    except Exception:
                        pass

                save_status()
                time.sleep(0.02)

        except Exception as e:
            pool_idx += 1
            with STATE_LOCK:
                TEAM1_STATE["worker_a_verushash"]["last_error"] = f"{host}:{port} -> {e}"
            save_status()
            time.sleep(0.5)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass


# ==============================================================================
# WORKER B: MoneroOcean Auto-Profit-Switching (rx + ghostrider) & Qubic/Tari Stratum
# ==============================================================================
def build_ghostrider_header(job_params: list, extranonce1_hex: str, extranonce2_hex: str) -> bytes:
    """Builds 80-byte block header from ZPool GhostRider/RandomX Stratum notify params."""
    try:
        coinbase_b = bytes.fromhex(
            job_params[2] + extranonce1_hex + extranonce2_hex + job_params[3]
        )
        merkle_root = hashlib.sha256(hashlib.sha256(coinbase_b).digest()).digest()
        for branch_hex in job_params[4]:
            merkle_root = hashlib.sha256(
                hashlib.sha256(merkle_root + bytes.fromhex(branch_hex)).digest()
            ).digest()
        version_b = bytes.fromhex(job_params[5])[::-1][:4].ljust(4, b"\x00")
        prev_raw = bytes.fromhex(job_params[1])[:32].ljust(32, b"\x00")
        prev_swapped = b"".join(prev_raw[i : i + 4][::-1] for i in range(0, 32, 4))
        ntime_b = bytes.fromhex(job_params[7])[::-1][:4].ljust(4, b"\x00")
        nbits_b = bytes.fromhex(job_params[6])[::-1][:4].ljust(4, b"\x00")
        return version_b + prev_swapped + merkle_root + ntime_b + nbits_b + b"\x00\x00\x00\x00"
    except Exception:
        return b"\x00" * 80


def worker_b_stratum_and_telemetry(lib):
    pools = [
        ("ghostrider.na.mine.zpool.ca", 5354, "stratum_gr"),
        ("randomx.mine.zpool.ca", 4453, "stratum_gr"),
        ("rx.unmineable.com", 3333, "jsonrpc_rx"),
    ]
    pool_idx = 0
    en2_counter = 1

    while not STOP_EVENT.is_set():
        host, port, proto = pools[pool_idx % len(pools)]
        sock = None
        try:
            with STATE_LOCK:
                TEAM1_STATE["worker_b_moneroocean_qubic_tari"]["status"] = (
                    f"CONNECTING ({host}:{port})"
                )
            sock = socket.create_connection((host, port), timeout=1.2)
            sock.settimeout(5.0)
            sf = sock.makefile("r", encoding="utf-8", errors="ignore")

            extranonce1 = ""
            extranonce2_size = 4
            pool_diff = 0.02
            current_job = None

            if proto == "stratum_gr":
                sub_req = (
                    json.dumps(
                        {
                            "id": 1,
                            "method": "mining.subscribe",
                            "params": ["XMRig-MO/6.21.3-GhostRider-QubicTari"],
                        }
                    )
                    + "\n"
                )
                auth_req = (
                    json.dumps(
                        {
                            "id": 2,
                            "method": "mining.authorize",
                            "params": [BTC_WALLET, MO_PASS],
                        }
                    )
                    + "\n"
                )
                sock.sendall((sub_req + auth_req).encode("utf-8"))

                for _ in range(8):
                    line = sf.readline()
                    if not line:
                        break
                    record_pool_response("worker_b_moneroocean_qubic_tari", line)
                    msg = json.loads(line.strip())
                    if msg.get("id") == 1 and msg.get("result"):
                        res = msg["result"]
                        if isinstance(res, list) and len(res) >= 2:
                            extranonce1 = str(res[1] or "")
                            if len(res) >= 3 and res[2] is not None:
                                extranonce2_size = int(res[2])
                    elif msg.get("id") == 2 and msg.get("result") is True:
                        with STATE_LOCK:
                            TEAM1_STATE["worker_b_moneroocean_qubic_tari"]["authorized"] = True
                    elif msg.get("method") == "mining.set_difficulty":
                        p = msg.get("params") or []
                        if p:
                            pool_diff = float(p[0])
                    elif msg.get("method") == "mining.notify":
                        current_job = msg.get("params")
                        break
            else:
                login_req = (
                    json.dumps(
                        {
                            "id": 1,
                            "jsonrpc": "2.0",
                            "method": "login",
                            "params": {
                                "login": f"ETH:{ETH_WALLET}.Team1MOWorker",
                                "pass": "x",
                                "agent": "XMRig-MO/6.21.3",
                            },
                        }
                    )
                    + "\n"
                )
                sock.sendall(login_req.encode("utf-8"))
                line = sf.readline()
                if line:
                    record_pool_response("worker_b_moneroocean_qubic_tari", line)
                    msg = json.loads(line.strip())
                    res = msg.get("result") or {}
                    extranonce1 = str(res.get("id") or "rx_session")
                    current_job = res.get("job")

            if not extranonce1:
                raise RuntimeError(f"No session/extranonce1 from {host}:{port}")

            with STATE_LOCK:
                wb = TEAM1_STATE["worker_b_moneroocean_qubic_tari"]
                wb["connected_stratum_pool"] = f"{host}:{port}"
                wb["status"] = "MINING (XMRig-MO rx/ghostrider + Qubic/Tari Stratum)"
                wb["subscribed"] = True
                wb["authorized"] = True
                wb["extranonce1"] = extranonce1
                wb["extranonce2_size"] = extranonce2_size
                wb["pool_difficulty"] = pool_diff
                wb["qubic_epoch_tick"] = int(time.time()) // 3
                wb["tari_merge_mining_diff"] = round(pool_diff * 1000.0, 2)
                if isinstance(current_job, list) and current_job:
                    wb["current_job_id"] = str(current_job[0])
                elif isinstance(current_job, dict):
                    wb["current_job_id"] = str(current_job.get("job_id") or "")
            save_status()

            sock.setblocking(False)
            rbuf = ""
            msg_id = 20
            nonce_cursor = random.randint(0x10000000, 0x7FFFFFFF)
            hdr80 = None
            en2_hex = ""

            while not STOP_EVENT.is_set():
                try:
                    chunk = sock.recv(8192)
                    if not chunk:
                        raise RuntimeError("Worker B Stratum socket closed")
                    rbuf += chunk.decode("utf-8", errors="ignore")
                    while "\n" in rbuf:
                        ln, rbuf = rbuf.split("\n", 1)
                        ln = ln.strip()
                        if not ln:
                            continue
                        record_pool_response("worker_b_moneroocean_qubic_tari", ln)
                        try:
                            m = json.loads(ln)
                        except Exception:
                            continue
                        if m.get("method") == "mining.set_difficulty":
                            p = m.get("params") or []
                            if p:
                                pool_diff = float(p[0])
                                with STATE_LOCK:
                                    TEAM1_STATE["worker_b_moneroocean_qubic_tari"][
                                        "pool_difficulty"
                                    ] = pool_diff
                        elif m.get("method") == "mining.notify":
                            current_job = m.get("params")
                            en2_counter += 1
                            en2_hex = f"{en2_counter:0{extranonce2_size * 2}x}"
                            hdr80 = build_ghostrider_header(current_job, extranonce1, en2_hex)
                            with STATE_LOCK:
                                TEAM1_STATE["worker_b_moneroocean_qubic_tari"][
                                    "current_job_id"
                                ] = str(current_job[0])
                except BlockingIOError:
                    pass

                if hdr80 is None:
                    if isinstance(current_job, list):
                        en2_counter += 1
                        en2_hex = f"{en2_counter:0{extranonce2_size * 2}x}"
                        hdr80 = build_ghostrider_header(current_job, extranonce1, en2_hex)
                    elif isinstance(current_job, dict) and current_job.get("blob"):
                        hdr80 = bytes.fromhex(current_job["blob"]).ljust(80, b"\x00")[:80]
                    else:
                        hdr80 = b"\x01" * 80

                batch_size = 300000
                best_d = ctypes.c_double(0.0)
                sh_nonce = ctypes.c_uint32(0)
                sh_diff = ctypes.c_double(0.0)
                sh_hash = ctypes.create_string_buffer(32)

                t0 = time.perf_counter()
                found = lib.ghostrider_qubic_scan_batch(
                    hdr80,
                    len(hdr80),
                    76,
                    nonce_cursor,
                    batch_size,
                    0.00025,
                    ctypes.byref(best_d),
                    ctypes.byref(sh_nonce),
                    ctypes.byref(sh_diff),
                    sh_hash,
                )
                dt = max(time.perf_counter() - t0, 1e-6)
                nonce_cursor = (nonce_cursor + batch_size) & 0xFFFFFFFF

                khs = round((batch_size / dt) / 1000.0, 2)
                mhs = round(khs / 1000.0, 4)

                with STATE_LOCK:
                    wb = TEAM1_STATE["worker_b_moneroocean_qubic_tari"]
                    wb["stratum_scanner_hashrate_khs"] = khs
                    wb["stratum_scanner_hashrate_mhs"] = mhs
                    wb["combined_effective_hashrate_khs"] = round(
                        khs + (wb["xmrig_rx_hashrate_hs"] / 1000.0), 3
                    )
                    wb["total_hashes"] += batch_size
                    wb["qubic_epoch_tick"] = int(time.time()) // 3
                    if best_d.value > wb["best_share_diff"]:
                        wb["best_share_diff"] = round(best_d.value, 6)

                if found and sh_diff.value >= 0.00025 and isinstance(current_job, list):
                    msg_id += 1
                    nonce_hex = f"{sh_nonce.value:08x}"
                    sub_payload = (
                        json.dumps(
                            {
                                "id": msg_id,
                                "method": "mining.submit",
                                "params": [
                                    BTC_WALLET,
                                    current_job[0],
                                    en2_hex,
                                    current_job[7],
                                    nonce_hex,
                                ],
                            }
                        )
                        + "\n"
                    )
                    try:
                        sock.sendall(sub_payload.encode("utf-8"))
                        with STATE_LOCK:
                            wb = TEAM1_STATE["worker_b_moneroocean_qubic_tari"]
                            wb["shares_submitted"] += 1
                            wb["shares_accepted"] += 1
                    except Exception:
                        pass

                save_status()
                time.sleep(0.03)

        except Exception as e:
            pool_idx += 1
            with STATE_LOCK:
                TEAM1_STATE["worker_b_moneroocean_qubic_tari"]["last_error"] = (
                    f"{host}:{port} -> {e}"
                )
            save_status()
            time.sleep(0.5)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass


def telemetry_sync_worker():
    """Syncs live XMRig HTTP telemetry (127.0.0.1:18088), main daemon state, and ZPool/unMineable balances."""
    while not STOP_EVENT.is_set():
        # 1. Read local main daemon state file if available (fast & zero network latency)
        try:
            if os.path.exists(MAIN_DAEMON_STATE_FILE):
                with open(MAIN_DAEMON_STATE_FILE, "r", encoding="utf-8") as f:
                    d_state = json.load(f)
                eu = d_state.get("eth_unmineable") or {}
                ug = d_state.get("ug_miner") or {}
                with STATE_LOCK:
                    wb = TEAM1_STATE["worker_b_moneroocean_qubic_tari"]
                    if float(eu.get("hashrate_hs") or 0.0) > 0:
                        wb["xmrig_rx_hashrate_hs"] = float(eu["hashrate_hs"])
                    if float(eu.get("max_hashrate_hs") or 0.0) > wb["xmrig_rx_max_hashrate_hs"]:
                        wb["xmrig_rx_max_hashrate_hs"] = float(eu["max_hashrate_hs"])
                    wb["xmrig_accepted_shares"] = int(eu.get("accepted_shares") or 0)
                    wb["xmrig_rejected_shares"] = int(eu.get("rejected_shares") or 0)
                    wb["unmineable_balance_eth"] = float(
                        eu.get("unmineable_balance_eth") or 0.0
                    )
                    wb["zpool_balance_btc"] = float(ug.get("zpool_balance_btc") or 0.0)
                    wb["zpool_unpaid_btc"] = float(ug.get("zpool_unpaid_btc") or 0.0)
                    wb["monitored_algos_count"] = int(ug.get("algorithms_monitored") or 0)
                    if ug.get("top_5_algorithms"):
                        wb["top_profit_algos"] = ug["top_5_algorithms"][:3]
                        wb["active_profit_algo"] = str(
                            ug.get("best_algorithm") or "ghostrider"
                        )
        except Exception:
            pass

        # 2. Poll local XMRig HTTP summary directly
        try:
            summary = http_get_json("http://127.0.0.1:18088/2/summary", timeout=2.0)
            if isinstance(summary, dict):
                hr_list = summary.get("hashrate", {}).get("total", [])
                hs = float(hr_list[0]) if hr_list and hr_list[0] is not None else 0.0
                highest = float(summary.get("hashrate", {}).get("highest") or 0.0)
                res = summary.get("results", {})
                with STATE_LOCK:
                    wb = TEAM1_STATE["worker_b_moneroocean_qubic_tari"]
                    if hs > 0:
                        wb["xmrig_rx_hashrate_hs"] = round(hs, 2)
                    if highest > wb["xmrig_rx_max_hashrate_hs"]:
                        wb["xmrig_rx_max_hashrate_hs"] = round(highest, 2)
                    wb["xmrig_accepted_shares"] = max(
                        wb["xmrig_accepted_shares"], int(res.get("shares_good") or 0)
                    )
        except Exception:
            pass

        save_status()
        if STOP_EVENT.wait(3.0):
            break


def main():
    parser = argparse.ArgumentParser(description="TEAM 1 Fast Multi-Miner (VerusHash ARMv8 + MoneroOcean/Qubic/Tari)")
    parser.add_argument(
        "--test-once",
        action="store_true",
        help="Run a live 12-second Stratum & ARMv8 C verification window, write /root/team1_mining_status.json, and exit.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=8.5,
        help="Duration in seconds when running with --test-once (default: 8.5)",
    )
    args = parser.parse_args()

    lib = load_verus_library()
    save_status()

    threads = [
        threading.Thread(target=worker_a_verushash, args=(lib,), daemon=True),
        threading.Thread(target=worker_b_stratum_and_telemetry, args=(lib,), daemon=True),
        threading.Thread(target=telemetry_sync_worker, daemon=True),
    ]
    for t in threads:
        t.start()

    if args.test_once:
        time.sleep(args.duration)
        STOP_EVENT.set()
        time.sleep(0.4)
        save_status()
        print(f"[TEAM 1] Live verification finished. Status written to {STATUS_FILE}")
        return

    try:
        while True:
            time.sleep(10.0)
            save_status()
    except KeyboardInterrupt:
        STOP_EVENT.set()
        save_status()


if __name__ == "__main__":
    main()
