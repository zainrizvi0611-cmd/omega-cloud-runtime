#!/usr/bin/env python3
"""
Bitcoin Puzzle #67/#68/#69/#71 ARMv8 Hardware-Accelerated Kangaroo & Keyhunt Daemon.
Loads /root/libbtcpuzzle_arm64.so (secp256k1 128-point Montgomery batch inversion +
ARMv8 vsha256hq_u32 + RIPEMD-160), verifies Puzzle #66 test vector, and continuously
scans random Kangaroo/stride subranges across Puzzles #67, #68, #69, and #71.
"""

import argparse
import ctypes
import json
import os
import secrets
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

SO_PATH = "/root/libbtcpuzzle_arm64.so"
STATUS_PATH = "/root/team2_kangaroo_status.json"
FOUND_PATH = "/root/BTC_PUZZLE_FOUND_KEYS.json"

PUZZLE_RANGES = {
    67: {
        "btc": 6.7,
        "address": "1BY8GQbnueYofwSuFAT3USAhGjPrkxDdW9",
        "hash160": "739437bb3dd6d1983e66629c5f08c70e52769371",
        "start": 0x40000000000000000,
        "end":   0x7FFFFFFFFFFFFFFFF,
    },
    68: {
        "btc": 6.8,
        "address": "1MVDYgVaSN6iKKEsbzRUAYFrYJadLYZvvZ",
        "hash160": "e0b8a2baee1b77fc703455f39d51477451fc8cfc",
        "start": 0x80000000000000000,
        "end":   0xFFFFFFFFFFFFFFFFF,
    },
    69: {
        "btc": 6.9,
        "address": "19vkiEajfhuZ8bs8Zu2jgmC6oqZbWqhxhG",
        "hash160": "61eb8a50c86b0584bb727dd65bed8d2400d6d5aa",
        "start": 0x100000000000000000,
        "end":   0x1FFFFFFFFFFFFFFFFF,
    },
    71: {
        "btc": 7.1,
        "address": "1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU",
        "hash160": "f6f5431d25bbf7b12e8add9af5e3475c44a0a5b8",
        "start": 0x400000000000000000,
        "end":   0x7FFFFFFFFFFFFFFFFF,
    },
}


def load_engine(so_path: str = SO_PATH):
    lib = ctypes.CDLL(so_path)
    lib.puzzle_self_test.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.puzzle_self_test.restype = ctypes.c_int

    lib.puzzle_scan_range.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
    ]
    lib.puzzle_scan_range.restype = ctypes.c_int
    return lib


def run_self_test(lib) -> dict:
    buf = ctypes.create_string_buffer(1024)
    rc = lib.puzzle_self_test(buf, 1024)
    data = json.loads(buf.value.decode("utf-8"))
    data["rc"] = rc
    return data


def pick_random_stride(puzzle_id: int, batch_keys: int) -> tuple[int, int]:
    info = PUZZLE_RANGES[puzzle_id]
    span = info["end"] - info["start"] - batch_keys
    offset = secrets.randbelow(span)
    start_k = info["start"] + offset
    return start_k, start_k + batch_keys - 1


def record_hit(hit_record: dict):
    existing = []
    if os.path.exists(FOUND_PATH):
        try:
            with open(FOUND_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    existing.append(hit_record)
    tmp = FOUND_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    os.replace(tmp, FOUND_PATH)


def write_status(status: dict):
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)
    os.replace(tmp, STATUS_PATH)


def scan_chunk(lib, start_k: int, batch_keys: int) -> dict | None:
    hi = (start_k >> 64) & 0xFFFFFFFFFFFFFFFF
    lo = start_k & 0xFFFFFFFFFFFFFFFF

    found_id = ctypes.c_int(0)
    found_hi = ctypes.c_uint64(0)
    found_lo = ctypes.c_uint64(0)
    pubkey = (ctypes.c_uint8 * 33)()
    h160 = (ctypes.c_uint8 * 20)()

    rc = lib.puzzle_scan_range(
        ctypes.c_uint64(hi),
        ctypes.c_uint64(lo),
        ctypes.c_uint64(batch_keys),
        ctypes.byref(found_id),
        ctypes.byref(found_hi),
        ctypes.byref(found_lo),
        pubkey,
        h160,
    )
    if rc != 0:
        priv = (found_hi.value << 64) | found_lo.value
        return {
            "puzzle_id": found_id.value,
            "privkey_hex": hex(priv),
            "pubkey_hex": bytes(pubkey).hex(),
            "hash160_hex": bytes(h160).hex(),
            "timestamp": time.time(),
        }
    return None


def main():
    parser = argparse.ArgumentParser(description="Bitcoin Puzzle #67/#68/#69/#71 ARMv8 Scanner Daemon")
    parser.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    parser.add_argument("--batch-keys", type=int, default=65536)
    parser.add_argument("--max-batches", type=int, default=0, help="0 = run indefinitely")
    args = parser.parse_args()

    lib = load_engine(SO_PATH)
    self_test = run_self_test(lib)
    if not self_test.get("passed"):
        raise RuntimeError(f"Puzzle #66 self-test failed: {self_test}")

    total_keys_checked = 0
    t_start = time.monotonic()
    cycle_puzzles = [67, 68, 67, 68, 69, 71]
    batch_idx = 0

    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        while True:
            futures = []
            ranges_this_round = []
            for t in range(args.threads):
                pid = cycle_puzzles[(batch_idx + t) % len(cycle_puzzles)]
                start_k, end_k = pick_random_stride(pid, args.batch_keys)
                ranges_this_round.append((pid, start_k, end_k))
                futures.append(pool.submit(scan_chunk, lib, start_k, args.batch_keys))

            t0 = time.monotonic()
            for fut in futures:
                hit = fut.result()
                if hit is not None and hit["puzzle_id"] != 66:
                    record_hit(hit)
            dt = max(1e-6, time.monotonic() - t0)

            round_keys = args.threads * args.batch_keys
            total_keys_checked += round_keys
            batch_idx += args.threads

            last_pid, last_start, last_end = ranges_this_round[-1]
            inst_kps = round_keys / dt
            avg_kps = total_keys_checked / max(1e-6, time.monotonic() - t_start)

            status = {
                "engine": "libbtcpuzzle_arm64.so (ARMv8 secp256k1 128-pt Montgomery + vsha256hq_u32 + RIPEMD160)",
                "puzzle66_self_test_passed": bool(self_test["passed"]),
                "puzzle66_verification": self_test,
                "keys_per_sec": round(inst_kps, 2),
                "avg_keys_per_sec": round(avg_kps, 2),
                "total_keys_checked": total_keys_checked,
                "active_puzzle": last_pid,
                "current_range_hex": f"{hex(last_start)}..{hex(last_end)}",
                "threads": args.threads,
                "batch_size_keys": args.batch_keys,
                "targets_monitored": [67, 68, 69, 71],
                "updated_at": time.time(),
            }
            write_status(status)

            if args.max_batches > 0 and batch_idx >= args.max_batches:
                break


if __name__ == "__main__":
    main()
