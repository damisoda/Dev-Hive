import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _latest_json() -> Path:
    raw_dir = Path("data/raw")
    files = sorted(raw_dir.glob("velog_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError("data/raw/velog_*.json 파일 없음. 먼저 크롤러를 실행하세요.")
    return files[0]


def run_eval(json_path: str | None = None) -> None:
    path = Path(json_path) if json_path else _latest_json()
    print("=" * 55)
    print(f"Velog Crawler Eval - {path.name}")
    print("=" * 55)

    with open(path, encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        print("수집된 항목 없음")
        return

    body_present = [i for i in items if i.get("body")]
    likes_list = [i["engagement"]["likes"] for i in items]
    comments_list = [i["engagement"]["comments"] for i in items]

    print(f"\n[수집 결과]")
    print(f"  총 수집: {len(items)}건")
    print(f"  body 있음: {len(body_present)}건 ({len(body_present) / len(items) * 100:.1f}%)")

    print(f"\n[engagement 분포]")
    print(f"  likes    min={min(likes_list)}  max={max(likes_list)}  avg={sum(likes_list)/len(likes_list):.1f}")
    print(f"  comments min={min(comments_list)}  max={max(comments_list)}  avg={sum(comments_list)/len(comments_list):.1f}")

    print(f"\n[날짜 범위]")
    dates = sorted(set(i["published_at"][:10] for i in items))
    print(f"  {dates[0]} ~ {dates[-1]} ({len(dates)}일)")

    all_tags: list[str] = []
    for item in items:
        # body에 태그 정보가 없으므로 title 기반 author 분포 확인
        all_tags.extend(item.get("tags", []) if "tags" in item else [])

    authors = Counter(i.get("author_name", "") for i in items)
    print(f"\n[작성자 분포 (상위 10명)]")
    for author, count in authors.most_common(10):
        print(f"  {author}: {count}건")

    print(f"\n[샘플 3건]")
    top3 = sorted(items, key=lambda x: x["engagement"]["likes"], reverse=True)[:3]
    for item in top3:
        body_info = f"있음 ({len(item['body'])}자)" if item.get("body") else "None"
        print(f"  제목  : {item['title'][:60]}")
        print(f"  작성자: {item.get('author_name', '-')}")
        print(f"  URL   : {item['url']}")
        print(f"  body  : {body_info}")
        print(f"  likes : {item['engagement']['likes']}  comments: {item['engagement']['comments']}")
        print()

    print("=" * 55)


if __name__ == "__main__":
    path_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_eval(path_arg)
