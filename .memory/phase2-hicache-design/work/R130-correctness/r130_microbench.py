#!/usr/bin/env python3
"""R130 microbenchmark: full-directory scan vs per-key metadata-cache lookup.

Offline, no GPU, no server. Compares the two branches of
``HiCacheFile._collect_existing_component_keys``:

  * ``metadata_cache is None`` -> ``os.scandir`` over the *whole* directory
    (cost scales with total files, independent of how many keys are asked);
  * ``metadata_cache`` populated -> per-key ``MetadataCache.contains`` and,
    on a miss/expiry, one ``os.path.exists`` + re-add (cost scales with keys).

Synthetic corpus is created under this authorized work directory and removed
afterwards. Optionally also measures the *real* L3 directory read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import sys
import tempfile
import time

from sglang.srt.mem_cache.hicache_storage import MetadataCache

HERE = os.path.dirname(os.path.abspath(__file__))
SUFFIX = "_R130test_0_1"
REAL_L3 = "/mnt/data/neuron/sglang-3090-r112-20260911/l3"
# The dispatch's target numbers for the real L3 corpus.
REAL_FILES = 3_090_000
REAL_KEYS = 12_000
DEFAULT_TTL = 5.0


def median_time(fn, rounds):
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times), times


def create_corpus(path, n, suffix=SUFFIX):
    for i in range(n):
        p = os.path.join(path, f"{i:08d}{suffix}.bin")
        os.close(os.open(p, os.O_WRONLY | os.O_CREAT, 0o600))


def bench_scandir_classify(path, target_files, rounds):
    """Replicates the metadata_cache-is-None branch of collect."""

    def run():
        found = set()
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_file() and entry.name in target_files:
                    found.add(entry.name)
        return found

    return median_time(run, rounds)


def bench_listdir_suffix(path, suffix, rounds, do_stat=False):
    """Replicates _scan_existing_files_to_metadata_cache (do_stat=False)
    and the evictor's _scan_existing_files (do_stat=True)."""

    def run():
        found = set()
        for fn in os.listdir(path):
            if not fn.endswith(".bin"):
                continue
            stem = fn[:-4]
            if not stem.endswith(suffix):
                continue
            if do_stat:
                try:
                    os.stat(os.path.join(path, fn))
                except OSError:
                    continue
            found.add(stem)
        return found

    return median_time(run, rounds)


def bench_contains_hot(cache, stems, rounds):
    def run():
        hits = 0
        for stem in stems:
            if cache.contains(stem):
                hits += 1
        return hits

    return median_time(run, rounds)


def bench_contains_revalidate(cache, stems, directory, rounds):
    """Worst case: every contains() misses, forcing one os.path.exists + add."""

    def run():
        present = 0
        for stem in stems:
            if cache.contains(stem):
                present += 1
                continue
            if os.path.exists(os.path.join(directory, f"{stem}.bin")):
                cache.add(stem)
                present += 1
        return present

    return median_time(run, rounds)


def bench_path_exists(directory, stems, rounds):
    def run():
        n = 0
        for stem in stems:
            if os.path.exists(os.path.join(directory, f"{stem}.bin")):
                n += 1
        return n

    return median_time(run, rounds)


def ns_per(total_seconds, n):
    return total_seconds / n * 1e9


def sec_per(seconds, n, scale):
    return seconds / n * scale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=100_000)
    ap.add_argument("--keys", type=int, default=12_000)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--real-l3", dest="real_l3", action="store_true", default=True)
    ap.add_argument("--no-real-l3", dest="real_l3", action="store_false")
    args = ap.parse_args()

    result = {"meta": vars(args), "synthetic": {}, "real_l3": {}, "projection": {}}

    # ---------------------------------------------------------------- synthetic
    print(f"[synth] creating {args.files:,} .bin files ...", flush=True)
    base = tempfile.mkdtemp(dir=HERE, prefix="_bench_")
    try:
        create_corpus(base, args.files)
        all_stems = [f"{i:08d}{SUFFIX}" for i in range(args.files)]
        target_keys = all_stems[: args.keys]
        target_files = {f"{s}.bin" for s in target_keys}

        scan_s, scan_r = bench_scandir_classify(base, target_files, args.rounds)
        list_s, list_r = bench_listdir_suffix(base, SUFFIX, args.rounds)
        liststat_s, liststat_r = bench_listdir_suffix(
            base, SUFFIX, args.rounds, do_stat=True
        )

        # Populated RAM index: all synthetic stems present, never expire.
        hot = MetadataCache(-1.0)
        for stem in all_stems:
            hot.add(stem)
        hot_s, hot_r = bench_contains_hot(hot, target_keys, max(args.rounds, 5))

        # Forced-expiry cache: every contains() misses -> revalidation path.
        cold = MetadataCache(-0.5)
        for stem in target_keys:
            cold.add(stem)
        reval_s, reval_r = bench_contains_revalidate(
            cold, target_keys, base, max(args.rounds, 5)
        )
        exists_s, exists_r = bench_path_exists(base, target_keys, max(args.rounds, 5))

        syn = result["synthetic"]
        syn["files"] = args.files
        syn["keys"] = args.keys
        syn["scandir_classify_seconds"] = scan_s
        syn["scandir_classify_ns_per_file"] = ns_per(scan_s, args.files)
        syn["listdir_suffix_seconds"] = list_s
        syn["listdir_suffix_ns_per_file"] = ns_per(list_s, args.files)
        syn["listdir_suffix_stat_seconds"] = liststat_s
        syn["listdir_suffix_stat_ns_per_file"] = ns_per(liststat_s, args.files)
        syn["contains_hot_seconds"] = hot_s
        syn["contains_hot_ns_per_key"] = ns_per(hot_s, args.keys)
        syn["contains_revalidate_seconds"] = reval_s
        syn["contains_revalidate_ns_per_key"] = ns_per(reval_s, args.keys)
        syn["path_exists_seconds"] = exists_s
        syn["path_exists_ns_per_key"] = ns_per(exists_s, args.keys)
        syn["raw_scandir_seconds"] = scan_r
        syn["raw_listdir_seconds"] = list_r
        syn["raw_contains_hot_seconds"] = hot_r
        syn["raw_contains_revalidate_seconds"] = reval_r

        print(
            f"[synth] scandir+classify {ns_per(scan_s, args.files):.0f} ns/file | "
            f"listdir+suffix {ns_per(list_s, args.files):.0f} ns/file | "
            f"contains(hot) {ns_per(hot_s, args.keys):.0f} ns/key | "
            f"contains+reval {ns_per(reval_s, args.keys):.0f} ns/key | "
            f"path.exists {ns_per(exists_s, args.keys):.0f} ns/key",
            flush=True,
        )
    finally:
        shutil.rmtree(base, ignore_errors=True)
        print(f"[synth] corpus removed: {base}", flush=True)

    # --------------------------------------------------------------- real L3
    real = {}
    if args.real_l3 and os.path.isdir(REAL_L3):
        print(f"[real] listing {REAL_L3} ...", flush=True)
        t0 = time.perf_counter()
        names = os.listdir(REAL_L3)
        listdir_only = time.perf_counter() - t0
        n_real = len(names)
        real["path"] = REAL_L3
        real["entries"] = n_real
        real["listdir_only_seconds"] = listdir_only
        real["listdir_only_ns_per_file"] = ns_per(listdir_only, n_real)
        print(f"[real] {n_real:,} entries, listdir {listdir_only:.3f}s", flush=True)

        classified = 0
        t0 = time.perf_counter()
        for fn in names:
            if fn.endswith(".bin"):
                classified += 1
        cls_s = time.perf_counter() - t0
        real["listdir_suffix_classify_seconds"] = cls_s
        real["listdir_suffix_classify_ns_per_file"] = ns_per(cls_s, n_real)
        real["bin_entries"] = classified

        sample = random.Random(130).sample(names, min(REAL_KEYS, n_real))
        target_real = set(sample)
        found = 0
        t0 = time.perf_counter()
        with os.scandir(REAL_L3) as entries:
            for entry in entries:
                if entry.is_file() and entry.name in target_real:
                    found += 1
        scan_real = time.perf_counter() - t0
        real["scandir_classify_seconds"] = scan_real
        real["scandir_classify_ns_per_file"] = ns_per(scan_real, n_real)
        real["scandir_classify_found"] = found

        t0 = time.perf_counter()
        for fn in sample:
            os.path.exists(os.path.join(REAL_L3, fn))
        real_exists_s = time.perf_counter() - t0
        real["path_exists_seconds"] = real_exists_s
        real["path_exists_ns_per_key"] = ns_per(real_exists_s, len(sample))

        print(
            f"[real] scandir+classify {real['scandir_classify_ns_per_file']:.0f} ns/file "
            f"({scan_real:.3f}s) | suffix-classify {real['listdir_suffix_classify_ns_per_file']:.0f} ns/file "
            f"| path.exists {real['path_exists_ns_per_key']:.0f} ns/key",
            flush=True,
        )
    elif args.real_l3:
        real["error"] = f"missing dir {REAL_L3}"
    result["real_l3"] = real

    # -------------------------------------------------------------- projection
    proj = result["projection"]
    scan_ns = result["synthetic"]["scandir_classify_ns_per_file"]
    list_ns = result["synthetic"]["listdir_suffix_ns_per_file"]
    hot_ns = result["synthetic"]["contains_hot_ns_per_key"]
    reval_ns = result["synthetic"]["contains_revalidate_ns_per_key"]
    exists_ns = result["synthetic"]["path_exists_ns_per_key"]

    proj["target_files"] = REAL_FILES
    proj["target_keys"] = REAL_KEYS
    proj["projected_scandir_full_scan_seconds"] = sec_per(scan_ns / 1e9, 1, REAL_FILES)
    proj["projected_listdir_full_scan_seconds"] = sec_per(list_ns / 1e9, 1, REAL_FILES)
    proj["projected_contains_hot_seconds"] = hot_ns / 1e9 * REAL_KEYS
    proj["projected_contains_reval_seconds"] = reval_ns / 1e9 * REAL_KEYS
    proj["projected_path_exists_seconds"] = exists_ns / 1e9 * REAL_KEYS
    proj["scan_over_reval_ratio"] = (
        proj["projected_scandir_full_scan_seconds"]
        / max(proj["projected_contains_reval_seconds"], 1e-12)
    )
    proj["scan_over_hot_ratio"] = (
        proj["projected_scandir_full_scan_seconds"]
        / max(proj["projected_contains_hot_seconds"], 1e-12)
    )

    # TTL amortisation: each key revalidates at most once per TTL window.
    ttl = DEFAULT_TTL
    queries_per_window = 50.0  # 12k-key query every 100 ms
    proj["ttl_seconds"] = ttl
    proj["scenario_queries_per_ttl_window"] = queries_per_window
    proj["scenario_amortized_revalidations_per_query"] = REAL_KEYS / queries_per_window
    proj["scenario_amortized_reval_seconds_per_query"] = (
        REAL_KEYS / queries_per_window * reval_ns / 1e9
    )

    if real.get("entries"):
        proj["real_measured_full_scan_seconds"] = real["scandir_classify_seconds"]
        proj["real_measured_listdir_seconds"] = real["listdir_only_seconds"]

    text = json.dumps(result, indent=2, sort_keys=True)
    with open(os.path.join(HERE, "_r130_microbench.json"), "w") as fh:
        fh.write(text + "\n")

    print("\n===== R130 MICROBENCH SUMMARY =====")
    print(f"synthetic files={args.files:,} keys={args.keys:,} rounds>={args.rounds}")
    print(f"  scandir+classify : {scan_ns:10.0f} ns/file")
    print(f"  listdir+suffix   : {list_ns:10.0f} ns/file")
    print(f"  contains (hot)   : {hot_ns:10.0f} ns/key")
    print(f"  contains+reval   : {reval_ns:10.0f} ns/key")
    print(f"  os.path.exists   : {exists_ns:10.0f} ns/key")
    print("projection to 3.09M files / 12k keys:")
    print(
        f"  full scandir scan : {proj['projected_scandir_full_scan_seconds']:.3f} s"
    )
    print(
        f"  full listdir scan : {proj['projected_listdir_full_scan_seconds']:.3f} s"
    )
    print(f"  hot per-key       : {proj['projected_contains_hot_seconds']*1e3:.3f} ms")
    print(
        f"  reval per-key     : {proj['projected_contains_reval_seconds']*1e3:.3f} ms"
    )
    print(
        f"  scan/hot ratio    : {proj['scan_over_hot_ratio']:.0f}x  "
        f"scan/reval ratio: {proj['scan_over_reval_ratio']:.0f}x"
    )
    if real.get("entries"):
        print(
            f"real L3: {real['entries']:,} files; measured scandir+classify "
            f"{real['scandir_classify_seconds']:.3f}s, listdir {real['listdir_only_seconds']:.3f}s"
        )
    print(f"json -> {os.path.join(HERE, '_r130_microbench.json')}")


if __name__ == "__main__":
    sys.exit(main())
