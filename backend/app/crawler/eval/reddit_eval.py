"""
Reddit Public Crawler eval — 수집 품질 빠른 점검.

실행 (backend/ 디렉터리에서):
    python app/crawler/eval/reddit_eval.py
    python app/crawler/eval/reddit_eval.py --path data/raw/reddit_public_20260608.json
    python app/crawler/eval/reddit_eval.py --sample 10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _latest_json() -> Path:
    raw_dir = Path("data/raw")
    files = sorted(raw_dir.glob("reddit_public_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError("data/raw/reddit_public_*.json 없음. 크롤러를 먼저 실행하세요.")
    return files[0]


def run_eval(json_path: str | None = None, sample: int = 5) -> None:
    path = Path(json_path) if json_path else _latest_json()
    print("=" * 60)
    print(f"Reddit Public Crawler Eval - {path.name}")
    print("=" * 60)

    items: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    if not items:
        print("수집된 항목 없음")
        return

    body_present = [i for i in items if i.get("body")]
    likes_list = [i["engagement"]["likes"] for i in items]
    comments_list = [i["engagement"]["comments"] for i in items]
    body_lens = [len(i["body"]) for i in body_present]

    print(f"\n[수집 결과]")
    print(f"  총 수집:      {len(items)}건")
    print(f"  body 있음:   {len(body_present)}건 ({len(body_present)/len(items)*100:.1f}%)")

    print(f"\n[body 길이]")
    print(f"  min={min(body_lens)}  max={max(body_lens)}  avg={sum(body_lens)//len(body_lens)}")

    print(f"\n[engagement - Arctic Shift 아카이빙 시점 값, 참고용]")
    print(f"  likes    min={min(likes_list)}  max={max(likes_list)}  avg={sum(likes_list)/len(likes_list):.1f}")
    print(f"  comments min={min(comments_list)}  max={max(comments_list)}  avg={sum(comments_list)/len(comments_list):.1f}")

    print(f"\n[날짜 범위]")
    dates = sorted(set(i["published_at"][:10] for i in items))
    print(f"  {dates[0]} ~ {dates[-1]} ({len(dates)}일)")

    # 서브레딧 분포 — URL에서 r/<sub> 추출
    subreddits: list[str] = []
    for i in items:
        parts = (i.get("url") or "").split("/")
        try:
            r_idx = parts.index("r")
            subreddits.append(parts[r_idx + 1])
        except (ValueError, IndexError):
            subreddits.append("unknown")

    print(f"\n[서브레딧 분포]")
    for sub, cnt in Counter(subreddits).most_common():
        print(f"  r/{sub}: {cnt}건")

    print(f"\n[상위 {sample}건 — 좋아요 순]")
    top = sorted(items, key=lambda x: x["engagement"]["likes"], reverse=True)[:sample]
    for idx, item in enumerate(top, 1):
        blen = len(item.get("body") or "")
        print(f"\n  [{idx}] {item['title'][:70]}")
        print(f"       URL    : {item['url']}")
        print(f"       body   : {blen}자")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reddit Public Crawler eval")
    parser.add_argument("--path", help="평가할 JSON 파일 경로 (기본: 최신 reddit_public_*.json)")
    parser.add_argument("--sample", type=int, default=5, help="출력할 샘플 수 (기본: 5)")
    args = parser.parse_args()
    run_eval(json_path=args.path, sample=args.sample)


if __name__ == "__main__":
    main()
