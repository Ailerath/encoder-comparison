#!/usr/bin/env python3
"""
main.py : measure time vs size between two methods of file

Huffman     very fast compression method
Arithmetic  can reduce the size further at the cost of time to compress

The script simply feeds every file in ./data/ to both coders, captures the
CPU time and peak RAM for compression(and optionally decompression), and outputs a CSV

Usage:
    python main.py            #Runs on ./data/ with no decompression
    python main.py --verify   #Runs on ./data/ and verifies decompression integrity
"""

import argparse
import csv
import mimetypes
import time
import tracemalloc
from pathlib import Path
from statistics import median

from coders.huffman import HuffmanCoder
from coders.arithmetic import ArithmeticCoder

#
#Utility helpers
#

def file_kind(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path)
    return(mime or "binary/unknown").split("/")[0]

def measure(coder, data: bytes, verify: bool):
    """Compress (and optionally decompress) data with coder.

    We track time via time.perf_counter and peak memory via
    tracemalloc so the numbers are unaffected by other processes

    Parameters
    ----------
    coder   : instance with .encode/.decode
    data    : raw bytes to feed in
    verify  : if True, we also decode and assert round‑trip integrity

    Returns a dict whose keys land directly in the CSV.
    """
    #Compression pass
    tracemalloc.start()
    t0 = time.perf_counter()
    encoded = coder.encode(data)
    t1 = time.perf_counter()
    _, peak_enc = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    out ={
        "compressed_size": len(encoded),
        "compression_time_ms": round((t1-t0)*1000, 3),
        "compression_mem_kb": round(peak_enc/1024, 2),
    }

    #Optional decompression pass
    if verify:
        tracemalloc.start()
        t2 = time.perf_counter()
        decoded = coder.decode(encoded)
        t3 = time.perf_counter()
        _, peak_dec = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        #Single byte mismatch means the coder failed.
        if decoded != data:
            raise ValueError(f"{coder.name}: round‑trip failed(data corrupted)")
        
        out["decompressed_size"] = len(decoded)

        out.update(
            decompression_time_ms=round((t3-t2)*1000, 3),
            decompression_mem_kb=round(peak_dec/1024, 2),
        )

    return out


#
#Main driver
#

def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Huffman vs Arithmetic coding.")
    parser.add_argument(
        "--verify", action="store_true",
        help="additionally decodes and confirms that output = input for algorithm integrity"
    )
    args = parser.parse_args()
    args.verify = True #personal terminal broke lol

    #Discover inputs
    files = sorted(Path("data").iterdir())
    if not files:
        raise SystemExit("No files in ./data to test against.")

    #Prep outputs
    Path("results").mkdir(exist_ok=True)
    coders = [HuffmanCoder(), ArithmeticCoder()]

    header = [
        "file", "type", "algorithm", "original_size", "compressed_size",
        "compression_ratio", "compression_time_ms", "compression_mem_kb",
    ]
    if args.verify:
        header += ["decompressed_size", "decompression_time_ms", "decompression_mem_kb"]
    else:
        print("[info] Decompression skipped, use --verify for full round‑trip test.")

    #Collect file deltas to show resulting median value.
    size_diffs: list[int] = []
    time_diffs: list[float] = []

    #Main loop
    with open("results/results.csv", "w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=header)
        writer.writeheader()

        for path in files:
            if not path.is_file() or path.name.lower() == "desktop.ini":
                continue

            data = path.read_bytes()
            orig_size = len(data)
            kind = file_kind(path)
            per_file: dict[str, dict] ={}

            for coder in coders:
                try:
                    metrics = measure(coder, data, verify=args.verify)
                except Exception as exc:
                    #If file fails, skips and continues to next file
                    print(f"[warn] {coder.name} failed on {path.name}:{exc}")
                    continue

                row ={
                    "file": path.name,
                    "type": kind,
                    "algorithm": coder.name,
                    "original_size": orig_size,
                    "compressed_size": metrics["compressed_size"],
                    "compression_ratio":(
                        round(orig_size/metrics["compressed_size"], 3)
                        if metrics["compressed_size"] else None
                    ),
                    "compression_time_ms": metrics["compression_time_ms"],
                    "compression_mem_kb": metrics["compression_mem_kb"],
                }
                if args.verify and "decompression_time_ms" in metrics:
                    row.update(
                        decompressed_size=metrics["decompressed_size"],
                        decompression_time_ms=metrics["decompression_time_ms"],
                        decompression_mem_kb=metrics["decompression_mem_kb"],
                    )

                writer.writerow(row)
                per_file[coder.name] = row

            #File summary
            if{"Huffman", "Arithmetic"} <= per_file.keys():
                h, a = per_file["Huffman"], per_file["Arithmetic"]
                size_diff = h["compressed_size"]-a["compressed_size"]
                time_diff = h["compression_time_ms"]-a["compression_time_ms"]
                size_diffs.append(size_diff)
                time_diffs.append(time_diff)

                pct = lambda d, base: round((d/base)*100, 2) if base else 0
                print(f"\n{path.name}")
                print(f"  Huffman    ratio {h['compression_ratio']} | time {h['compression_time_ms']} ms")
                print(f"  Arithmetic ratio {a['compression_ratio']} | time {a['compression_time_ms']} ms")
                print(f"  Size {size_diff:+} bytes({pct(size_diff, a['compressed_size']):+}%)")
                print(f"  Time {time_diff:+.3f} ms({pct(time_diff, a['compression_time_ms']):+}%)")

    #Aggregate summary
    if size_diffs:
        print("\nMedian differences across all test files:")
        print(f"  size {median(size_diffs):+.0f} bytes (Huffman-Arithmetic)")
        print(f"  time {median(time_diffs):+.3f} ms")

    print("\nDone.  Results saved to results/results.csv")


if __name__ == "__main__":
    main()

