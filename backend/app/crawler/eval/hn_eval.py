import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _latest_json() -> Path:
    raw_dir = Path("data/raw")
    files = sorted(raw_dir.glob("hackernews_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError("data/raw/hackernews_*.json 파일 없음. 먼저 크롤러를 실행하세요.")
    return files[0]


def run_eval(json_path: str | None = None) -> None:
    path = Path(json_path) if json_path else _latest_json()
    print("=" * 50)
    print(f"HN Crawler Eval - {path.name}")
    print("=" * 50)

    with open(path, encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        print("수집된 항목 없음")
        return

    stories  = [i for i in items if not i["title"].startswith("[HN comment]")]
    comments = [i for i in items if i["title"].startswith("[HN comment]")]
    body_none = [i for i in items if not i.get("body")]

    print(f"\n[수집 결과]")
    print(f"  총 수집 (중복 제거): {len(items)}건")
    print(f"  story  : {len(stories)}건")
    print(f"  comment: {len(comments)}건")
    print(f"  body=None: {len(body_none)}건 ({len(body_none) / len(items) * 100:.1f}%)")

    print(f"\n[engagement 분포]")
    likes_list = [i["engagement"]["likes"] for i in stories]
    if likes_list:
        print(f"  likes    min={min(likes_list)}  max={max(likes_list)}  avg={sum(likes_list)/len(likes_list):.1f}")
    comments_list = [i["engagement"]["comments"] for i in stories]
    if comments_list:
        print(f"  comments min={min(comments_list)}  max={max(comments_list)}  avg={sum(comments_list)/len(comments_list):.1f}")

    print(f"\n[샘플 3건]")
    for item in items[:3]:
        print(f"  제목  : {item['title'][:70]}")
        print(f"  URL   : {item['url']}")
        print(f"  body  : {'있음 (' + str(len(item['body'])) + '자)' if item.get('body') else 'None'}")
        print(f"  likes : {item['engagement']['likes']}  comments: {item['engagement']['comments']}")
        print()

    print("=" * 50)


if __name__ == "__main__":
    path_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_eval(path_arg)
