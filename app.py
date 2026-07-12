#!/usr/bin/env python3
"""
YouTube 키워드 수집 도구 - 웹앱 버전

브라우저에서 키워드를 입력하고 버튼을 눌러 수집하고, 쌓인 데이터를 표로 본다.
수집/엑셀 로직은 collect.py, view.py 를 그대로 재사용한다 (한 코드, 여러 입구).

실행:
    python app.py

그러면 이 맥에서 웹 서버가 켜진다. 화면에 뜨는 주소로 접속하면 된다.
  - 이 맥에서:      http://127.0.0.1:8000
  - 같은 와이파이 폰: http://<맥의 IP>:8000   (실행하면 정확한 주소를 알려줌)

멈추려면 터미널에서 Control + C.
"""

import socket
import sqlite3
import sys

from flask import (
    Flask,
    render_template_string,
    request,
    redirect,
    url_for,
    send_file,
    flash,
    abort,
)

import collect  # run_collection() 재사용
import view     # build_xlsx() 재사용

app = Flask(__name__)
# flash 메시지(한 번 보여주고 사라지는 알림)를 쓰려면 secret_key 가 필요하다.
# 로컬 개인용이라 아무 값이나 넣어도 된다.
app.secret_key = "youtube-keyword-tracker-local"

DB_FILE = collect.DB_FILE
PORT = 8000


# ---------------------------------------------------------------------------
# DB 읽기 도우미 (읽기 전용 — 수집은 collect.run_collection 이 담당)
# ---------------------------------------------------------------------------
def query(sql, params=()):
    """DB 에서 읽어와 사전(dict) 리스트로 돌려준다. 화면에 쓰기 편하게."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # 컬럼 이름으로 값을 꺼낼 수 있게
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_exists() -> bool:
    import os
    return os.path.exists(DB_FILE)


# ---------------------------------------------------------------------------
# 화면(HTML) 템플릿
#   Jinja2 가 자동으로 <, > 같은 특수문자를 안전하게 처리해준다(HTML 주입 방지).
# ---------------------------------------------------------------------------
STYLE = """
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif;
    max-width: 900px; margin: 0 auto; padding: 16px; line-height: 1.5;
  }
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1.1rem; margin-top: 28px; }
  a { color: #2563eb; }
  form.collect {
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
    background: rgba(127,127,127,0.08); padding: 14px; border-radius: 12px;
  }
  input[type=text], input[type=number] {
    padding: 12px; font-size: 16px; border: 1px solid #ccc; border-radius: 8px;
  }
  input[name=keyword] { flex: 1 1 200px; min-width: 0; }
  input[type=number] { width: 90px; }
  button {
    padding: 12px 18px; font-size: 16px; border: 0; border-radius: 8px;
    background: #2563eb; color: white; cursor: pointer;
  }
  button.secondary { background: #6b7280; }
  .msg { padding: 12px; border-radius: 8px; margin: 12px 0;
         background: #dcfce7; color: #065f46; }
  .msg.err { background: #fee2e2; color: #991b1b; }
  .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  table { border-collapse: collapse; width: 100%; margin-top: 8px; font-size: 14px; }
  th, td { border: 1px solid rgba(127,127,127,0.3); padding: 8px; text-align: left;
           white-space: nowrap; }
  td.wrap { white-space: normal; min-width: 200px; }
  .hint { color: #6b7280; font-size: 13px; }
  .num { text-align: right; }
</style>
"""

INDEX_HTML = """
<!doctype html>
<html lang="ko">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube 키워드 수집기</title>{{ style|safe }}</head>
<body>
  <h1>🔎 YouTube 키워드 수집기</h1>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, text in messages %}
      <div class="msg {{ 'err' if category == 'error' else '' }}">{{ text }}</div>
    {% endfor %}
  {% endwith %}

  <form class="collect" method="post" action="{{ url_for('do_collect') }}"
        onsubmit="this.querySelector('button').innerText='수집 중… (20~30초)'; this.querySelector('button').disabled=true;">
    <input type="text" name="keyword" placeholder="키워드 입력 (예: AmazeVR)" required autofocus>
    <input type="number" name="max_videos" value="20" min="1" max="50" title="영상 수">
    <input type="number" name="max_comments" value="20" min="1" max="100" title="영상당 댓글 수">
    <button type="submit">수집하기</button>
  </form>
  <p class="hint">영상 수 · 영상당 댓글 수. 수집은 20~30초쯤 걸려요. 같은 키워드를 다시 하면 새 기록으로 쌓입니다.</p>

  <h2>📋 지금까지 수집한 기록 ({{ searches|length }}건)</h2>
  {% if searches %}
  <p><a href="{{ url_for('export') }}">⬇️ 전체 데이터 엑셀(.xlsx)로 내려받기</a></p>
  <div class="table-wrap">
  <table>
    <tr><th>번호</th><th>키워드</th><th>수집시각(UTC)</th><th>영상</th><th>댓글</th><th></th></tr>
    {% for s in searches %}
    <tr>
      <td>{{ s.id }}</td>
      <td>{{ s.keyword }}</td>
      <td>{{ s.collected_at }}</td>
      <td class="num">{{ s.video_count }}</td>
      <td class="num">{{ s.comment_count }}</td>
      <td><a href="{{ url_for('detail', search_id=s.id) }}">상세보기</a></td>
    </tr>
    {% endfor %}
  </table>
  </div>
  {% else %}
  <p class="hint">아직 수집한 게 없어요. 위에서 키워드를 입력하고 수집해보세요.</p>
  {% endif %}
</body></html>
"""

DETAIL_HTML = """
<!doctype html>
<html lang="ko">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>수집 #{{ search.id }} - {{ search.keyword }}</title>{{ style|safe }}</head>
<body>
  <p><a href="{{ url_for('index') }}">← 목록으로</a></p>
  <h1>#{{ search.id }} · "{{ search.keyword }}"</h1>
  <p class="hint">수집시각(UTC): {{ search.collected_at }} · 영상 {{ search.video_count }}개 · 댓글 {{ search.comment_count }}개</p>

  <h2>🎬 영상 (조회수 높은 순)</h2>
  <div class="table-wrap">
  <table>
    <tr><th>제목</th><th>채널</th><th>조회수</th><th>좋아요</th><th>댓글수</th><th>링크</th></tr>
    {% for v in videos %}
    <tr>
      <td class="wrap">{{ v.title }}</td>
      <td>{{ v.channel_title }}</td>
      <td class="num">{{ '{:,}'.format(v.view_count) if v.view_count is not none else '' }}</td>
      <td class="num">{{ '{:,}'.format(v.like_count) if v.like_count is not none else '' }}</td>
      <td class="num">{{ '{:,}'.format(v.comment_count) if v.comment_count is not none else '' }}</td>
      <td><a href="{{ v.url }}" target="_blank">보기</a></td>
    </tr>
    {% endfor %}
  </table>
  </div>

  <h2>💬 댓글 (좋아요 많은 순)</h2>
  <div class="table-wrap">
  <table>
    <tr><th>작성자</th><th>댓글</th><th>좋아요</th><th>작성일</th></tr>
    {% for c in comments %}
    <tr>
      <td>{{ c.author }}</td>
      <td class="wrap">{{ c.text }}</td>
      <td class="num">{{ '{:,}'.format(c.like_count) if c.like_count is not none else '' }}</td>
      <td>{{ c.published_at }}</td>
    </tr>
    {% endfor %}
  </table>
  </div>
</body></html>
"""


# ---------------------------------------------------------------------------
# 화면 주소(라우트)
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    searches = []
    if db_exists():
        searches = query(
            "SELECT id, keyword, collected_at, video_count, comment_count "
            "FROM searches ORDER BY id DESC;"
        )
    return render_template_string(INDEX_HTML, style=STYLE, searches=searches)


@app.route("/collect", methods=["POST"])
def do_collect():
    keyword = (request.form.get("keyword") or "").strip()
    if not keyword:
        flash("키워드를 입력해주세요.", "error")
        return redirect(url_for("index"))

    # 숫자 칸이 비었거나 이상하면 기본값으로. YouTube 한도에 맞춰 범위도 정리.
    max_videos = _clamp(request.form.get("max_videos"), collect.DEFAULT_MAX_VIDEOS, 1, 50)
    max_comments = _clamp(request.form.get("max_comments"), collect.DEFAULT_MAX_COMMENTS, 1, 100)

    try:
        result = collect.run_collection(keyword, max_videos, max_comments)
    except RuntimeError as e:
        # 키 없음 / 쿼터 초과 / API 오류 등 → 화면에 빨간 알림
        flash(str(e), "error")
        return redirect(url_for("index"))

    note = " (쿼터 초과로 중간에 멈춤)" if result["quota_exceeded"] else ""
    flash(
        f'"{result["keyword"]}" 수집 완료 · 영상 {result["video_count"]}개, '
        f'댓글 {result["comment_count"]}개 (쿼터 ~{result["quota_used"]} units){note}',
        "ok",
    )
    return redirect(url_for("index"))


@app.route("/search/<int:search_id>")
def detail(search_id):
    if not db_exists():
        abort(404)
    rows = query("SELECT * FROM searches WHERE id = ?;", (search_id,))
    if not rows:
        abort(404)
    search = rows[0]
    videos = query(
        "SELECT * FROM videos WHERE search_id = ? ORDER BY view_count DESC;",
        (search_id,),
    )
    comments = query(
        "SELECT * FROM comments WHERE search_id = ? ORDER BY like_count DESC;",
        (search_id,),
    )
    return render_template_string(
        DETAIL_HTML, style=STYLE, search=search, videos=videos, comments=comments
    )


@app.route("/export")
def export():
    try:
        result = view.build_xlsx()
    except FileNotFoundError:
        flash("아직 내려받을 데이터가 없어요. 먼저 수집해보세요.", "error")
        return redirect(url_for("index"))
    return send_file(
        result["path"], as_attachment=True, download_name="youtube_data.xlsx"
    )


def _clamp(raw, default, low, high):
    """폼에서 온 문자열 숫자를 정수로 바꾸고 low~high 범위로 자른다."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


def _lan_ip() -> str:
    """이 맥이 와이파이에서 갖는 IP 주소를 알아낸다. (폰에서 접속할 주소)"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # 실제로 보내진 않고 경로만 확인
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    ip = _lan_ip()
    print("=" * 60)
    print("웹 서버를 켰어요. 브라우저에서 아래 주소로 접속하세요:")
    print(f"  이 맥에서:        http://127.0.0.1:{PORT}")
    print(f"  같은 와이파이 폰:  http://{ip}:{PORT}")
    print("멈추려면 이 창에서 Control + C 를 누르세요.")
    print("=" * 60)
    # host="0.0.0.0" : 이 맥뿐 아니라 같은 와이파이의 다른 기기도 접속 허용
    app.run(host="0.0.0.0", port=PORT, debug=False)
