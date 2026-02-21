#!/usr/bin/env python3
"""
Data/yyyymmdd* 디렉토리를 입력으로 naver-poster 임시저장을 재현 실행한다.

사용 예:
  python3 scripts/repro_temp_save_from_data.py --dir data/20260212(장어)
  python3 scripts/repro_temp_save_from_data.py --dir data/20260212(장어) --runs 3
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

MARKER = "NAVER_POST_RESULT_JSON:"


def load_metadata(data_dir: Path) -> Dict[str, Any]:
    meta_path = data_dir / "metadata.json"
    blog_path = data_dir / "blog_result.md"
    info: Dict[str, Any] = {
        "title": None,
        "blocks": None,
        "place": None,
        "images": [],
    }
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            info["title"] = meta.get("title")
            info["place"] = meta.get("store_name") or meta.get("placeName")
            info["blocks"] = meta.get("blocks")
        except Exception:
            pass
    if blog_path.exists() and not info["title"]:
        for line in blog_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip():
                info["title"] = line.strip().lstrip("# ").strip()
                break
    images_dir = data_dir / "images"
    if images_dir.exists():
        info["images"] = [
            {"name": p.name, "size_bytes": p.stat().st_size}
            for p in sorted(images_dir.iterdir())
            if p.is_file()
        ]
    return info


def run_once(project_root: Path, data_dir: Path) -> Dict[str, Any]:
    naver_poster_root = project_root / "naver-poster"
    cli = naver_poster_root / "dist" / "cli" / "post_to_naver.js"
    if not cli.exists():
        raise RuntimeError(f"CLI not found: {cli}. run `cd naver-poster && npm run build` first.")

    cmd = ["node", str(cli), "--dir", str(data_dir.resolve())]
    proc = subprocess.run(
        cmd,
        cwd=str(naver_poster_root),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"CLI exit={proc.returncode}\n{output[-4000:]}")

    marker_line = None
    for line in output.splitlines():
        if MARKER in line:
            marker_line = line
    if not marker_line:
        raise RuntimeError(f"Result marker not found.\n{output[-4000:]}")

    payload = marker_line.split(MARKER, 1)[1].strip()
    return json.loads(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repro runner for naver temp save from data dir")
    parser.add_argument("--dir", required=True, help="data directory path (e.g. data/20260212(장어))")
    parser.add_argument("--runs", type=int, default=1, help="repeat count (default: 1)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    data_dir = (project_root / args.dir).resolve() if not Path(args.dir).is_absolute() else Path(args.dir).resolve()
    if not data_dir.exists():
        print(f"[FAIL] data dir not found: {data_dir}", file=sys.stderr)
        return 1

    meta = load_metadata(data_dir)
    print(f"[REPRO] dir={data_dir}")
    print(f"[REPRO] title={meta.get('title')}")
    print(f"[REPRO] place={meta.get('place')}")
    print(f"[REPRO] image_count={len(meta.get('images', []))}")
    if meta.get("images"):
        print("[REPRO] images:")
        for idx, image in enumerate(meta["images"], 1):
            print(f"  - #{idx} {image['name']} size={image['size_bytes']}")

    success = 0
    for i in range(1, args.runs + 1):
        print(f"\n[RUN {i}/{args.runs}] start")
        report = run_once(project_root, data_dir)
        draft_ok = bool(report.get("draft_summary", {}).get("success"))
        step_f = report.get("steps", {}).get("F", {})
        print(
            f"[RUN {i}] overall={report.get('overall_status')} "
            f"draft_ok={draft_ok} stepF={step_f.get('status')} image={report.get('image_summary', {}).get('status')}"
        )
        if not draft_ok or step_f.get("status") != "success":
            print(f"[RUN {i}] FAIL report={json.dumps(step_f, ensure_ascii=False)}")
            return 2
        success += 1

    print(f"\n[PASS] {success}/{args.runs} runs succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

