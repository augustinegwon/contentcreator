"""reference_XX.json 을 읽어서 같은 이름의 .md 요약본을 만든다.

사용법:  python3 analysis/build_md.py analysis/reference_01.json
JSON만 고치고 이 스크립트를 다시 돌리면 MD가 갱신된다. MD는 직접 고치지 않는다.
"""
import json
import sys
from pathlib import Path


def bullets(items, indent=""):
    return "\n".join(f"{indent}- {x}" for x in items)


def numbered(items):
    return "\n".join(f"{i}. {x}" for i, x in enumerate(items, 1))


def build(data):
    meta, video, overall = data["meta"], data["video"], data["overall"]
    out = []
    out.append(f"# 레퍼런스 영상 분석 - {meta['source_video']}\n")
    out.append("> 이 파일은 `build_md.py`로 JSON에서 자동 생성됨. 수정은 JSON에서 할 것.\n")
    out.append(f"- 분석 방법: {meta['analyzed_with']}")
    out.append(f"- 정확도: {meta['accuracy_note']}")
    out.append(f"- 개인정보: {meta['privacy_note']}")
    out.append(f"- **만들 범위**: {meta['target_note']}\n")

    out.append("## 영상 개요\n")
    out.append(f"- 길이: {video['duration_sec']}초 / {video['fps']}fps")
    out.append(f"- 캔버스: {video['canvas']}")
    out.append(f"- 구조: {video['format']}")
    out.append(f"- 편집 툴: {video['tool']}\n")

    out.append("## 전체 분위기·스타일\n")
    for k, label in [("mood", "분위기"), ("bgm", "BGM"), ("color_tone", "색감"),
                     ("font", "폰트"), ("edit_rhythm", "편집 리듬")]:
        out.append(f"- **{label}**: {overall[k]}")
    out.append("")

    out.append("## 장면 한눈에 보기\n")
    out.append("| # | 시간 | 장면 | 종류 | 확신도 |")
    out.append("|---|---|---|---|---|")
    for s in data["scenes"]:
        out.append(f"| {s['id']} | {s['start']}~{s['end']} | {s['title']} | {s['clip_type']} | {s['confidence']} |")
    out.append("")

    out.append("## 공통 레이어 (모든 장면에 고정)\n")
    out.append(data["layout"]["note"] + "\n")
    for i, layer in enumerate(data["layout"]["layers_bottom_to_top"], 1):
        out.append(f"{i}. **{layer['name']}**: {layer['detail']}")
    out.append("")

    out.append("## CapCut 공통 레시피\n")
    out.append(f"_{data['recipes']['menu_note']}_\n")
    for key, rec in data["recipes"].items():
        if key == "menu_note":
            continue
        out.append(f"### `{key}` - {rec['title']}\n")
        out.append(numbered(rec["steps"]))
        out.append("")

    out.append("## 장면별 편집 방법\n")
    for s in data["scenes"]:
        out.append(f"### {s['id']}. {s['title']} ({s['start']}~{s['end']})\n")
        out.append(f"{s['description']}\n")
        out.append(f"- **전환(들어올 때)**: {s['transition_in']}")
        out.append(f"- **전환(나갈 때)**: {s['transition_out']}")
        out.append(f"- **모션**: {s['motion']}")
        t = s["text"]
        out.append(f"- **텍스트**: {t['content']} / 애니메이션: {t['animation']} / 위치: {t['position']}")
        out.append(f"- **색감·필터**: {s['color_filter']}")
        out.append(f"- **속도**: {s['speed']}")
        out.append(f"- **오디오**: {s['audio']}")
        if s.get("beats"):
            out.append("- **세부 컷**:")
            out.append(bullets(s["beats"], "  "))
        out.append(f"- **사용 레시피**: {', '.join('`' + r + '`' for r in s['recipes'])}\n")
        out.append("**CapCut 작업 순서**\n")
        out.append(numbered(s["capcut_steps"]))
        if s.get("notes"):
            out.append(f"\n> 참고: {s['notes']}")
        out.append("")

    out.append("## 나중에 참고할 팁\n")
    out.append(bullets(data["reusable_tips"]))
    out.append("")
    out.append("## 아직 확실하지 않은 부분\n")
    out.append(bullets(data["unknowns"]))
    out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = src.with_suffix(".md")
    dst.write_text(build(json.loads(src.read_text(encoding="utf-8"))), encoding="utf-8")
    print(f"wrote {dst}")
