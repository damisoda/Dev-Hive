"""
Velog 시드 유저 후보 자동 추출 스크립트

7개 대주제별 대표 키워드로 searchPosts를 호출해
작성자별 총 좋아요·글 수·커버 도메인·경험글 비율을 집계한 뒤 상위 후보를 출력한다.
출력 결과를 팀이 검토해 velog_crawler.py 의 VELOG_SEED_USERS 에 추가한다.

실행 예시 (backend/ 디렉터리에서):
    python app/crawler/eval/velog_seed_finder.py
    python app/crawler/eval/velog_seed_finder.py --top 30 --min-posts 3
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

VELOG_GQL_URL = "https://v2.velog.io/graphql"
HTTP_TIMEOUT = 30
REQUEST_SLEEP = 0.5
PAGES_PER_KEYWORD = 3
PAGE_SIZE = 20

# 7개 대주제 → 대표 검색 키워드 매핑
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "프롬프트 엔지니어링": ["프롬프트엔지니어링", "프롬프트"],
    "Agentic AI":        ["에이전트", "MCP", "멀티에이전트", "claude code"],
    "멀티모달 AI":        ["이미지생성", "멀티모달"],
    "RAG & 지식 관리":   ["RAG", "임베딩", "벡터DB"],
    "오픈소스 AI":        ["ollama", "파인튜닝", "huggingface"],
    "AI 워크플로우 & 자동화": ["n8n", "자동화", "make.com"],
    "AI 엔지니어링":      ["MLOps", "LLMOps", "AI개발"],
}

# 경험글 직접 탐색용 키워드 — experience 모드에서 추가 검색
EXPERIENCE_KEYWORDS: dict[str, list[str]] = {
    "경험 콘텐츠": [
        "AI 후기", "AI 사용기", "AI 개발기",
        "claude 후기", "GPT 후기", "LLM 후기",
        "AI 삽질", "AI 시행착오",
        "n8n 후기", "ollama 후기", "RAG 후기",
        "에이전트 후기", "MCP 후기",
        # 입문 경험 타겟
        "처음 써봤", "처음 써본", "처음 사용해봤",
        "입문기", "도입기", "도입 후기",
        "마이그레이션", "codex 후기", "cursor 후기",
        "claude code 후기", "vibe coding",
        # 입문·중급 AI 코딩 도구 후기
        "cursor ai", "커서 ai", "코파일럿 후기", "github copilot 후기",
        "AI 코딩 후기", "AI 코딩 경험",
        # 입문자 관점
        "AI 입문", "AI 독학", "AI 공부",
        "챗GPT 활용", "ChatGPT 활용", "chatgpt 후기",
        "노코드 후기", "자동화 후기", "업무 자동화 후기",
    ],
}

# haiku_tagging_prompt.md content_type=experience 판단 신호어
# title + short_description 에서 하나라도 매칭되면 경험글로 분류
_EXPERIENCE_SIGNALS: tuple[str, ...] = (
    # 직접 해봤다는 표현
    "해봤", "써봤", "만들어봤", "적용해봤", "구축해봤", "붙여봤", "돌려봤",
    "사용해봤", "연결해봤", "써보니", "해보니", "만들어보니", "써본",
    # 결과/후기 표현
    "후기", "회고", "느낀점", "느낀 점", "삽질", "시행착오",
    "경험담", "경험기", "실제로", "실무에서", "실무 적용",
    # 과거형 직접 행동
    "구축했", "만들었", "개발했", "적용했", "활용했", "도입했",
    "연동했", "배포했", "마이그레이션했",
    # 배움/인사이트 공유
    "배웠", "알게됐", "알게 됐", "깨달",
    # 영어 표현
    "i built", "i tried", "i used", "we built", "we used",
    "lessons learned", "case study", "in production", "my experience",
)


def _is_experience(title: str, description: str) -> bool:
    text = (title + " " + description).lower()
    return any(sig in text for sig in _EXPERIENCE_SIGNALS)


_SEARCH_QUERY = """
query($keyword: String!, $limit: Int!, $offset: Int!) {
  searchPosts(keyword: $keyword, limit: $limit, offset: $offset) {
    posts {
      id
      url_slug
      title
      short_description
      user { username }
      tags
      likes
      released_at
    }
  }
}
"""


def _gql(keyword: str, offset: int) -> list[dict]:
    try:
        resp = requests.post(
            VELOG_GQL_URL,
            json={
                "query": _SEARCH_QUERY,
                "variables": {"keyword": keyword, "limit": PAGE_SIZE, "offset": offset},
            },
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("data") or {}).get("searchPosts", {}).get("posts") or []
    except requests.RequestException as exc:
        print(f"  [경고] {keyword} offset={offset} 요청 실패: {exc}")
        return []


def _collect(keyword_map: dict[str, list[str]], authors: dict[str, dict]) -> None:
    for domain, keywords in keyword_map.items():
        for keyword in keywords:
            print(f"  검색: [{domain}] '{keyword}'")
            for page in range(PAGES_PER_KEYWORD):
                posts = _gql(keyword, page * PAGE_SIZE)
                if not posts:
                    break
                for post in posts:
                    username = (post.get("user") or {}).get("username") or ""
                    if not username:
                        continue
                    authors[username]["total_likes"] += int(post.get("likes") or 0)
                    authors[username]["post_count"] += 1
                    authors[username]["domains"].add(domain)
                    if _is_experience(
                        post.get("title") or "",
                        post.get("short_description") or "",
                    ):
                        authors[username]["experience_posts"] += 1
                time.sleep(REQUEST_SLEEP)


def collect_candidates(experience_first: bool = False) -> dict[str, dict]:
    """username → {total_likes, post_count, experience_posts, domains} 형태로 집계"""
    authors: dict[str, dict] = defaultdict(
        lambda: {"total_likes": 0, "post_count": 0, "experience_posts": 0, "domains": set()}
    )
    _collect(DOMAIN_KEYWORDS, authors)
    if experience_first:
        _collect(EXPERIENCE_KEYWORDS, authors)
    return authors


def print_report(
    authors: dict[str, dict], top_n: int, min_posts: int, experience_first: bool = False
) -> None:
    filtered = {
        u: d for u, d in authors.items()
        if d["post_count"] >= min_posts
        and (not experience_first or d["experience_posts"] >= 1)
    }

    def _score(data: dict) -> float:
        exp_ratio = data["experience_posts"] / max(data["post_count"], 1)
        if experience_first:
            # 경험글 비율 우선, 좋아요는 보조
            return exp_ratio * (data["total_likes"] + 1) ** 0.4
        domain_weight = len(data["domains"]) ** 1.5
        likes_weight = (data["total_likes"] + 1) ** 0.6
        exp_bonus = 1 + exp_ratio
        return domain_weight * likes_weight * exp_bonus

    ranked = sorted(
        filtered.items(),
        key=lambda x: _score(x[1]),
        reverse=True,
    )[:top_n]

    print()
    print("=" * 80)
    print(f"Velog 시드 유저 후보 (상위 {len(ranked)}명, 최소 글 수: {min_posts})")
    print("=" * 80)
    print(f"{'순위':<4} {'username':<22} {'글수':>4} {'좋아요':>7} {'경험글':>5}  커버 도메인")
    print("-" * 80)
    for rank, (username, data) in enumerate(ranked, 1):
        exp_ratio = data["experience_posts"] / max(data["post_count"], 1)
        exp_str = f"{data['experience_posts']}({exp_ratio:.0%})"
        domains_str = ", ".join(sorted(data["domains"]))
        print(
            f"{rank:<4} {username:<22} {data['post_count']:>4} {data['total_likes']:>7}"
            f" {exp_str:>7}  {domains_str}"
        )
    print("=" * 80)
    print()
    print("# velog_crawler.py VELOG_SEED_USERS 에 추가할 후보 목록:")
    print("VELOG_SEED_USERS = [")
    for _, (username, _) in enumerate(ranked):
        print(f'    "{username}",')
    print("]")
    print()
    print("팀원이 각 계정을 직접 확인 후 양질의 작성자만 최종 목록에 포함하세요.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Velog 시드 유저 후보 자동 추출")
    parser.add_argument("--top", type=int, default=20, help="출력할 후보 수 (기본: 20)")
    parser.add_argument("--min-posts", type=int, default=2, help="최소 수집 글 수 (기본: 2)")
    parser.add_argument(
        "--experience-first", action="store_true",
        help="경험글 비율 우선 랭킹 + 경험 특화 키워드 추가 검색",
    )
    args = parser.parse_args()

    print("Velog 시드 유저 후보 탐색 중...")
    print(f"도메인 수: {len(DOMAIN_KEYWORDS)}, 페이지/키워드: {PAGES_PER_KEYWORD}")
    if args.experience_first:
        print("모드: 경험글 우선 (experience-first)")
    print()

    authors = collect_candidates(experience_first=args.experience_first)
    print(f"\n총 발견 작성자: {len(authors)}명")
    # experience-first 모드: 도메인 키워드 검색 결과에서만 경험글 비율로 재정렬
    # (경험 전용 키워드로 끌어온 비AI 유저는 도메인 집합에 "경험 콘텐츠"만 있으므로 제외)
    if args.experience_first:
        authors = {
            u: d for u, d in authors.items()
            if d["domains"] - {"경험 콘텐츠"}  # AI 도메인 키워드에서도 발견된 유저만
        }
        print(f"AI 도메인 필터 후: {len(authors)}명")
    print_report(authors, top_n=args.top, min_posts=args.min_posts, experience_first=args.experience_first)


if __name__ == "__main__":
    main()
