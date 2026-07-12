#!/usr/bin/env python3
"""
수집한 데이터를 엑셀/넘버스로 열 수 있게 CSV 파일로 뽑아주는 도구.

사용법:
    python view.py

실행하면 같은 폴더에 export 폴더가 생기고, 그 안에 CSV 3개가 만들어진다.
그 CSV 파일을 더블클릭하면 엑셀(Excel)이나 넘버스(Numbers)로 바로 열린다.

만드는 파일:
    export/searches.csv  - 언제 무슨 키워드를 수집했는지 (수집 이벤트 목록)
    export/videos.csv    - 수집한 영상들 (제목, 조회수, 좋아요 등)
    export/comments.csv  - 수집한 댓글들 (작성자, 내용, 좋아요 등)
"""

import csv
import os
import sqlite3
import sys

DB_FILE = "youtube_data.db"      # collect.py 가 만든 데이터 파일
EXPORT_DIR = "export"            # CSV 를 모아둘 폴더


# 뽑을 표 3개. (파일이름, SQL 쿼리) 형태.
# 사람이 보기 좋은 순서로 컬럼을 정렬해서 가져온다.
EXPORTS = {
    "searches.csv": """
        SELECT id AS 수집번호,
               keyword AS 키워드,
               collected_at AS 수집시각,
               video_count AS 영상수,
               comment_count AS 댓글수
        FROM searches
        ORDER BY id;
    """,
    "videos.csv": """
        SELECT search_id AS 수집번호,
               title AS 제목,
               channel_title AS 채널,
               view_count AS 조회수,
               like_count AS 좋아요,
               comment_count AS 댓글수,
               published_at AS 게시일,
               url AS 링크,
               collected_at AS 수집시각
        FROM videos
        ORDER BY search_id, view_count DESC;
    """,
    "comments.csv": """
        SELECT search_id AS 수집번호,
               video_id AS 영상ID,
               author AS 작성자,
               text AS 댓글내용,
               like_count AS 좋아요,
               published_at AS 작성일,
               collected_at AS 수집시각
        FROM comments
        ORDER BY search_id, like_count DESC;
    """,
}


def main() -> None:
    # 1) 데이터 파일이 있는지 먼저 확인한다.
    if not os.path.exists(DB_FILE):
        print(
            f"[에러] '{DB_FILE}' 파일이 없습니다.\n"
            "       먼저 수집을 한 번 해야 해요:  python collect.py \"키워드\"",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2) CSV 를 모아둘 폴더를 만든다. (이미 있으면 그냥 둠)
    os.makedirs(EXPORT_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)

    total_rows = 0
    for filename, query in EXPORTS.items():
        path = os.path.join(EXPORT_DIR, filename)
        rows = conn.execute(query).fetchall()
        # 컬럼 이름(한글 별칭)을 헤더로 쓴다.
        headers = [d[0] for d in conn.execute(query).description]

        # encoding="utf-8-sig": 엑셀에서 한글이 깨지지 않도록 BOM 을 붙인다.
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        print(f"  {filename:16s} → {len(rows):5d}줄")
        total_rows += len(rows)

    conn.close()

    # 3) 안내 출력
    folder = os.path.abspath(EXPORT_DIR)
    print("\n" + "=" * 60)
    print(f"CSV {len(EXPORTS)}개 저장 완료 (총 {total_rows}줄)")
    print(f"위치: {folder}")
    print("이 폴더의 .csv 파일을 더블클릭하면 엑셀/넘버스로 열려요.")
    print("=" * 60)


if __name__ == "__main__":
    main()
