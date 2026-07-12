# YouTube 키워드 수집 도구

특정 키워드에 대한 대중 반응을 **시계열로 추적**하기 위한 로컬 도구입니다.
키워드로 상위 영상과 댓글을 수집해 SQLite(`youtube_data.db`)에 계속 쌓아둡니다.
같은 키워드를 나중에 다시 실행하면 **덮어쓰지 않고 새 스냅샷으로 추가**됩니다.

**쓰는 방법은 두 가지** — 둘 다 같은 데이터(`youtube_data.db`)를 씁니다:
- **터미널(CLI)**: `python collect.py "키워드"` → `python view.py`
- **웹앱(브라우저)**: `python app.py` → 브라우저에서 접속해 버튼으로 사용 (폰에서도 가능, 아래 참고)

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

## 사용법 A) 웹앱 — 브라우저에서 (폰에서도 가능)

```bash
python app.py
```
실행하면 접속 주소가 화면에 뜹니다:
```
  이 맥에서:        http://127.0.0.1:8000
  같은 와이파이 폰:  http://192.168.0.5:8000   (숫자는 컴퓨터마다 다름)
```
- **이 맥**에서는 `http://127.0.0.1:8000` 접속.
- **폰**에서는 (맥과 **같은 와이파이**에 연결한 뒤) 화면에 뜬 `http://192.168...:8000` 주소를 브라우저에 입력.
- 키워드를 넣고 **수집하기** 버튼 → 표로 결과가 쌓이고, **엑셀로 내려받기**도 됩니다.
- 멈추려면 터미널에서 **Control + C**.

> 참고: 이 방식은 맥이 켜져 있고 `python app.py` 가 돌아가는 동안, **같은 와이파이 안에서만** 접속됩니다.

## 사용법 B) 터미널 — 명령어로

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

**방법 1) 엑셀/넘버스로 보기 (추천)**
```bash
python view.py
```
`youtube_data.xlsx` 파일 1개가 생깁니다. 안에 시트(탭) 3개(`수집기록`, `영상`, `댓글`)가
들어 있어요. 더블클릭하면 엑셀/넘버스로 바로 열립니다. (한글 안 깨짐)

**방법 2) 터미널에서 빠르게 확인**
```bash
sqlite3 youtube_data.db "SELECT id, keyword, collected_at, video_count, comment_count FROM searches;"
```

## 참고
- YouTube API 는 하루 무료 쿼터가 **10,000 units** 입니다.
  1회 실행(영상 20개)은 약 **121 units** 를 씁니다 → 하루 약 80회 실행 가능.
- 댓글이 꺼진 영상은 자동으로 건너뜁니다.
- 쿼터를 초과하면 안내 메시지를 출력하고, 그때까지 수집한 데이터는 저장됩니다.
