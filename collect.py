#!/usr/bin/env python3
"""
YouTube 키워드 수집 도구 (로컬 CLI)

특정 키워드에 대한 대중 반응을 시계열로 추적하기 위해,
키워드별 상위 영상과 댓글을 반복 수집해 SQLite 에 축적한다.

사용법:
    python collect.py "AmazeVR"
    python collect.py "AmazeVR" --max-videos 10 --max-comments 30

핵심 원칙:
    - 매 실행은 "새 스냅샷"으로 append 한다. 기존 데이터를 절대 덮어쓰지 않는다.
    - 같은 키워드를 나중에 다시 수집하면 시점별로 데이터가 쌓인다.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

# python-dotenv: .env 파일을 읽어 환경변수로 올려준다.
from dotenv import load_dotenv

# google-api-python-client: YouTube Data API 를 호출하는 공식 라이브러리.
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ---------------------------------------------------------------------------
# 설정값 (필요하면 여기 기본값만 바꾸면 된다)
# ---------------------------------------------------------------------------
DB_FILE = "youtube_data.db"          # 데이터가 쌓이는 SQLite 파일
DEFAULT_MAX_VIDEOS = 20              # 키워드당 수집할 영상 수
DEFAULT_MAX_COMMENTS = 20           # 영상당 수집할 댓글 수

# YouTube API 는 요청마다 "쿼터(quota)"를 소모한다. (하루 무료 한도: 10,000)
# 아래는 각 요청의 쿼터 비용이며, 실행 후 대략적인 소모량을 추정하는 데 쓴다.
QUOTA_SEARCH = 100                  # search.list 1회
QUOTA_VIDEOS = 1                    # videos.list 1회
QUOTA_COMMENTS = 1                  # commentThreads.list 1회


def utc_now_iso() -> str:
    """현재 시각을 UTC ISO8601 문자열로 반환한다. (예: 2026-07-11T12:34:56+00:00)"""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1) 데이터베이스 준비
# ---------------------------------------------------------------------------
def init_db(conn: sqlite3.Connection) -> None:
    """테이블 3개(searches, videos, comments)를 없으면 만든다.

    searches : 수집 이벤트(= 한 번의 실행 = 하나의 스냅샷) 1건 = 1행
    videos   : 그 스냅샷에서 수집한 영상들
    comments : 각 영상에서 수집한 댓글들

    videos/comments 는 search_id 로 어느 스냅샷에 속하는지 연결된다(외래 키).
    """
    # 외래 키 제약을 켠다. (SQLite 는 기본적으로 꺼져 있음)
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS searches (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword       TEXT    NOT NULL,
            collected_at  TEXT    NOT NULL,   -- 수집 시각 (UTC ISO8601)
            video_count   INTEGER NOT NULL,   -- 이번에 수집된 영상 수
            comment_count INTEGER NOT NULL    -- 이번에 수집된 댓글 수
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id      INTEGER NOT NULL,
            video_id       TEXT    NOT NULL,
            title          TEXT,
            channel_title  TEXT,
            channel_id     TEXT,
            published_at   TEXT,
            view_count     INTEGER,
            like_count     INTEGER,
            comment_count  INTEGER,
            url            TEXT,
            collected_at   TEXT    NOT NULL,
            FOREIGN KEY (search_id) REFERENCES searches(id)
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id     INTEGER NOT NULL,
            video_id      TEXT    NOT NULL,   -- 어느 영상의 댓글인지
            comment_id    TEXT,
            author        TEXT,
            text          TEXT,
            like_count    INTEGER,
            published_at  TEXT,
            collected_at  TEXT    NOT NULL,
            FOREIGN KEY (search_id) REFERENCES searches(id)
        );
        """
    )

    # 나중에 "특정 키워드/영상"으로 조회할 때 빨라지도록 인덱스를 만든다.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_searches_keyword ON searches(keyword);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_search ON videos(search_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_search ON comments(search_id);")
    conn.commit()


# ---------------------------------------------------------------------------
# 2) YouTube API 호출 함수들
# ---------------------------------------------------------------------------
def search_videos(youtube, keyword: str, max_videos: int) -> list[str]:
    """키워드로 영상을 검색해 video_id 목록을 반환한다. (order=relevance)"""
    response = (
        youtube.search()
        .list(
            q=keyword,
            part="id",
            type="video",
            order="relevance",
            maxResults=max_videos,
        )
        .execute()
    )

    video_ids = []
    for item in response.get("items", []):
        # 검색 결과 중 실제 영상(videoId 가 있는 것)만 추린다.
        vid = item.get("id", {}).get("videoId")
        if vid:
            video_ids.append(vid)
    return video_ids


def fetch_video_details(youtube, video_ids: list[str]) -> list[dict]:
    """video_id 목록에 대한 상세 메타데이터를 한 번의 요청으로 가져온다.

    videos.list 는 id 를 쉼표로 묶어 최대 50개까지 한 번에 조회할 수 있다.
    우리는 최대 20개이므로 한 번의 요청이면 충분하다.
    """
    if not video_ids:
        return []

    response = (
        youtube.videos()
        .list(
            part="snippet,statistics",
            id=",".join(video_ids),
        )
        .execute()
    )

    videos = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        vid = item.get("id")

        videos.append(
            {
                "video_id": vid,
                "title": snippet.get("title"),
                "channel_title": snippet.get("channelTitle"),
                "channel_id": snippet.get("channelId"),
                "published_at": snippet.get("publishedAt"),
                # 통계값은 문자열로 오거나 아예 없을 수 있어 안전하게 정수로 변환한다.
                "view_count": _to_int(stats.get("viewCount")),
                "like_count": _to_int(stats.get("likeCount")),
                "comment_count": _to_int(stats.get("commentCount")),
                "url": f"https://www.youtube.com/watch?v={vid}",
            }
        )
    return videos


def fetch_comments(youtube, video_id: str, max_comments: int) -> list[dict]:
    """한 영상의 상위 댓글을 가져온다. (order=relevance)

    댓글이 비활성화된 영상은 API 가 403 에러(commentsDisabled)를 낸다.
    그럴 때는 빈 리스트를 반환하고, 호출한 쪽에서 조용히 건너뛴다.
    """
    response = (
        youtube.commentThreads()
        .list(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=max_comments,
            textFormat="plainText",
        )
        .execute()
    )

    comments = []
    for item in response.get("items", []):
        # 최상위 댓글(대댓글 제외)의 실제 내용은 여기에 들어 있다.
        top = item["snippet"]["topLevelComment"]
        cid = top.get("id")
        c = top.get("snippet", {})
        comments.append(
            {
                "comment_id": cid,
                "author": c.get("authorDisplayName"),
                "text": c.get("textDisplay"),
                "like_count": _to_int(c.get("likeCount")),
                "published_at": c.get("publishedAt"),
            }
        )
    return comments


def _to_int(value):
    """API 가 준 값을 정수로 안전하게 변환한다. 없거나 변환 실패 시 None."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _is_comments_disabled(error: HttpError) -> bool:
    """이 HttpError 가 '댓글 비활성화' 때문인지 판별한다."""
    # error 내용에 'commentsDisabled' 문자열이 들어 있으면 댓글 비활성으로 본다.
    reason = ""
    try:
        # 최신 라이브러리는 error_details 에 사유를 담아준다.
        details = getattr(error, "error_details", None) or []
        reason = " ".join(str(d.get("reason", "")) for d in details)
    except Exception:
        pass
    return "commentsDisabled" in reason or "commentsDisabled" in str(error)


def _is_quota_exceeded(error: HttpError) -> bool:
    """이 HttpError 가 '일일 쿼터 초과' 때문인지 판별한다."""
    text = str(error)
    return "quotaExceeded" in text or "dailyLimitExceeded" in text


# ---------------------------------------------------------------------------
# 3) 저장 함수들 (모두 append — 절대 덮어쓰지 않음)
# ---------------------------------------------------------------------------
def insert_search(conn, keyword, collected_at) -> int:
    """이번 실행의 스냅샷 행을 먼저 만들고, 그 search_id 를 돌려준다.

    영상/댓글 수는 나중에 채우므로 일단 0으로 넣어 두고, 끝나면 갱신한다.
    """
    cur = conn.execute(
        "INSERT INTO searches (keyword, collected_at, video_count, comment_count) "
        "VALUES (?, ?, 0, 0);",
        (keyword, collected_at),
    )
    return cur.lastrowid


def insert_videos(conn, search_id, collected_at, videos: list[dict]) -> None:
    for v in videos:
        conn.execute(
            """
            INSERT INTO videos
                (search_id, video_id, title, channel_title, channel_id,
                 published_at, view_count, like_count, comment_count, url, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                search_id,
                v["video_id"],
                v["title"],
                v["channel_title"],
                v["channel_id"],
                v["published_at"],
                v["view_count"],
                v["like_count"],
                v["comment_count"],
                v["url"],
                collected_at,
            ),
        )


def insert_comments(conn, search_id, video_id, collected_at, comments: list[dict]) -> None:
    for c in comments:
        conn.execute(
            """
            INSERT INTO comments
                (search_id, video_id, comment_id, author, text,
                 like_count, published_at, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                search_id,
                video_id,
                c["comment_id"],
                c["author"],
                c["text"],
                c["like_count"],
                c["published_at"],
                collected_at,
            ),
        )


def update_search_counts(conn, search_id, video_count, comment_count) -> None:
    conn.execute(
        "UPDATE searches SET video_count = ?, comment_count = ? WHERE id = ?;",
        (video_count, comment_count, search_id),
    )


# ---------------------------------------------------------------------------
# 4) 메인 로직
# ---------------------------------------------------------------------------
def run_collection(keyword: str, max_videos: int, max_comments: int, log=None) -> dict:
    """키워드를 수집해 DB 에 저장하고, 결과 요약(dict)을 돌려준다.

    이 함수가 '진짜 일'을 하는 부분이다. 터미널(collect.py) 과 웹(app.py) 이
    둘 다 이 함수를 호출하므로, 수집 로직은 여기 한 곳에만 있다.

    log: 진행 상황을 알리고 싶을 때 넘기는 함수(예: print). 없으면 조용히 진행.
    반환: {keyword, video_count, comment_count, quota_used, search_id,
           quota_exceeded, db_path}
    치명적 오류(키 없음/API 실패)는 RuntimeError 로 올린다.
    """
    def _log(msg):
        if log:
            log(msg)

    # --- API 키 로드 ---------------------------------------------------------
    load_dotenv()  # 현재 폴더의 .env 파일을 읽어 환경변수로 올린다.
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY 를 찾을 수 없습니다. "
            ".env 파일에 발급받은 API 키를 넣어주세요."
        )

    # YouTube API 클라이언트를 만든다.
    youtube = build("youtube", "v3", developerKey=api_key)

    collected_at = utc_now_iso()  # 이번 스냅샷의 공통 타임스탬프
    quota_used = 0                # 소모 쿼터 추정치를 누적한다.
    quota_exceeded = False        # 중간에 쿼터가 터졌는지 표시

    # DB 연결 및 준비
    conn = sqlite3.connect(DB_FILE)
    init_db(conn)

    # 이번 실행의 스냅샷 행을 먼저 만든다. (부분 실패해도 기록이 남도록)
    search_id = insert_search(conn, keyword, collected_at)
    conn.commit()

    total_videos = 0
    total_comments = 0

    try:
        # --- 1. 키워드 검색 --------------------------------------------------
        _log(f'키워드 "{keyword}" 검색 중...')
        video_ids = search_videos(youtube, keyword, max_videos)
        quota_used += QUOTA_SEARCH

        if not video_ids:
            _log("검색 결과가 없습니다.")
            update_search_counts(conn, search_id, 0, 0)
            conn.commit()
        else:
            # --- 2. 영상 상세 메타데이터 ------------------------------------
            videos = fetch_video_details(youtube, video_ids)
            quota_used += QUOTA_VIDEOS
            insert_videos(conn, search_id, collected_at, videos)
            total_videos = len(videos)
            conn.commit()
            _log(f"영상 {total_videos}개 메타데이터 수집 완료.")

            # --- 3. 각 영상의 댓글 ------------------------------------------
            for i, v in enumerate(videos, start=1):
                vid = v["video_id"]
                try:
                    comments = fetch_comments(youtube, vid, max_comments)
                    quota_used += QUOTA_COMMENTS
                    insert_comments(conn, search_id, vid, collected_at, comments)
                    total_comments += len(comments)
                    conn.commit()
                    _log(f"  [{i}/{total_videos}] 댓글 {len(comments)}개 수집  ({v['title'][:40]})")
                except HttpError as e:
                    # 댓글 비활성 영상은 조용히 건너뛴다.
                    if _is_comments_disabled(e):
                        quota_used += QUOTA_COMMENTS  # 요청 자체는 나갔으므로 쿼터 소모
                        _log(f"  [{i}/{total_videos}] 댓글 비활성화 → 건너뜀  ({v['title'][:40]})")
                        continue
                    # 쿼터 초과면 중단하되, 지금까지 수집한 건 이미 저장돼 있다.
                    if _is_quota_exceeded(e):
                        quota_exceeded = True
                        _log("[중단] 일일 API 쿼터 초과. 지금까지 수집분은 저장됨.")
                        break
                    # 그 외 에러는 해당 영상만 건너뛰고 계속 진행한다.
                    _log(f"  [{i}/{total_videos}] 댓글 수집 중 에러(건너뜀): {e}")
                    continue

        # 최종 집계를 스냅샷 행에 기록한다.
        update_search_counts(conn, search_id, total_videos, total_comments)
        conn.commit()

    except HttpError as e:
        # 검색/영상조회 단계에서 난 에러 처리. 부분 결과라도 저장한다.
        update_search_counts(conn, search_id, total_videos, total_comments)
        conn.commit()
        if _is_quota_exceeded(e):
            raise RuntimeError(
                "일일 API 쿼터를 초과했습니다. 내일 다시 시도하거나 다른 API 키를 쓰세요."
            )
        raise RuntimeError(f"YouTube API 호출 실패: {e}")
    finally:
        conn.close()

    return {
        "keyword": keyword,
        "video_count": total_videos,
        "comment_count": total_comments,
        "quota_used": quota_used,
        "search_id": search_id,
        "quota_exceeded": quota_exceeded,
        "db_path": os.path.abspath(DB_FILE),
    }


def collect(keyword: str, max_videos: int, max_comments: int) -> None:
    """터미널용 진입점: run_collection 을 호출하고 사람이 읽기 좋게 출력한다."""
    try:
        result = run_collection(keyword, max_videos, max_comments, log=print)
    except RuntimeError as e:
        print(f"\n[에러] {e}", file=sys.stderr)
        sys.exit(1)

    _print_summary(
        result["keyword"],
        result["video_count"],
        result["comment_count"],
        result["quota_used"],
    )


def _print_summary(keyword, videos, comments, quota_used) -> None:
    print("\n" + "=" * 60)
    print(
        f'키워드 "{keyword}": 영상 {videos}개, 댓글 {comments}개 수집 완료 '
        f"(소요 쿼터 추정치 ~{quota_used} units / 일일 한도 10,000)"
    )
    print(f"저장 위치: {os.path.abspath(DB_FILE)}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 5) 명령줄 진입점
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube 키워드별 상위 영상/댓글을 수집해 SQLite 에 축적하는 도구."
    )
    parser.add_argument("keyword", help='검색할 키워드 (예: "AmazeVR")')
    parser.add_argument(
        "--max-videos",
        type=int,
        default=DEFAULT_MAX_VIDEOS,
        help=f"수집할 영상 수 (기본 {DEFAULT_MAX_VIDEOS}, 최대 50)",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=DEFAULT_MAX_COMMENTS,
        help=f"영상당 수집할 댓글 수 (기본 {DEFAULT_MAX_COMMENTS}, 최대 100)",
    )
    args = parser.parse_args()

    # YouTube API 한도에 맞춰 값을 정리한다.
    max_videos = max(1, min(args.max_videos, 50))
    max_comments = max(1, min(args.max_comments, 100))

    collect(args.keyword, max_videos, max_comments)


if __name__ == "__main__":
    main()
