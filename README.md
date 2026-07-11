# YouTube 키워드 수집 도구

특정 키워드에 대한 대중 반응을 **시계열로 추적**하기 위한 로컬 CLI 도구입니다.
키워드로 상위 영상과 댓글을 수집해 SQLite(`youtube_data.db`)에 계속 쌓아둡니다.
같은 키워드를 나중에 다시 실행하면 **덮어쓰지 않고 새 스냅샷으로 추가**됩니다.

## 처음 한 번만 하는 준비

### 1) 파이썬 라이브러리 설치
```bash
# (권장) 가상환경 만들기 — 컴퓨터를 깨끗하게 유지해줍니다
python3 -m venv .venv
source .venv/bin/activate          # 윈도우: .venv\Scripts\activate

# 필요한 라이브러리 설치
pip install -r requirements.txt
```

### 2) API 키 준비
1. https://console.cloud.google.com/ 에서 프로젝트를 만들고
2. **YouTube Data API v3** 를 "사용 설정"한 뒤
3. **API 키**를 발급받으세요.
4. 발급한 키를 `.env` 파일에 넣습니다:

```bash
cp .env.example .env
# 그런 다음 .env 파일을 열어 YOUTUBE_API_KEY 값을 실제 키로 바꾸세요
```

## 사용법

```bash
# 기본: 영상 20개 + 영상당 댓글 20개
python collect.py "AmazeVR"

# 개수 조절도 가능
python collect.py "AmazeVR" --max-videos 10 --max-comments 30
```

실행이 끝나면 이렇게 요약이 나옵니다:
```
키워드 "AmazeVR": 영상 20개, 댓글 380개 수집 완료 (소요 쿼터 추정치 ~121 units / 일일 한도 10,000)
```

## 저장 구조

`youtube_data.db` 안에 테이블 3개가 있습니다.

| 테이블 | 내용 |
|--------|------|
| `searches` | 실행(스냅샷) 1건 = 1행. 키워드, 수집 시각, 영상/댓글 수 |
| `videos` | 각 스냅샷에서 수집한 영상 메타데이터 (`search_id` 로 연결) |
| `comments` | 각 영상의 상위 댓글 (`search_id`, `video_id` 로 연결) |

### 쌓인 데이터 살펴보기
```bash
sqlite3 youtube_data.db "SELECT id, keyword, collected_at, video_count, comment_count FROM searches;"
```

## 참고
- YouTube API 는 하루 무료 쿼터가 **10,000 units** 입니다.
  1회 실행(영상 20개)은 약 **121 units** 를 씁니다 → 하루 약 80회 실행 가능.
- 댓글이 꺼진 영상은 자동으로 건너뜁니다.
- 쿼터를 초과하면 안내 메시지를 출력하고, 그때까지 수집한 데이터는 저장됩니다.
