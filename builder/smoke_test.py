"""CapCut(해외판) 드래프트가 맥에서 열리는지 확인하는 스모크 테스트.

사용법 (가상환경에 pycapcut==0.0.4 설치 필요):
    python builder/smoke_test.py

만들어지는 것 (builder/out/):
    smoke_1_basic    사진 + 영상 + 텍스트 (기능 최소)
    smoke_2_effects  마스크(Feather), 키프레임 줌, 디졸브, 페이드, 텍스트 등장 효과

드래프트는 소재를 '절대경로'로 참조한다. 경로는 __MEDIA_DIR__, __DRAFT_ROOT__ 로 만들어 두고
맥에서 install.sh 를 실행하면 실제 경로로 바뀐다. 결과물은 builder/out/smoke_test_pack.zip.
"""
import shutil
import time
import json
from pathlib import Path

import pycapcut as cc

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "my_assets"
OUT = ROOT / "builder" / "out"
PHOTO = "placeholder_photo.jpg"
VIDEO = "placeholder_video.mp4"

W, H, FPS = 1080, 1920, 24


def tr(start, duration):
    """초 단위 (시작, 길이) -> Timerange"""
    return cc.trange(f"{start}s", f"{duration}s")


def new_draft(folder, name):
    return folder.create_draft(name, W, H, fps=FPS, allow_replace=True)


def smoke_basic(folder):
    """기능을 최소로 쓴 드래프트. 이게 안 열리면 버전/경로 문제."""
    d = new_draft(folder, "smoke_1_basic")
    d.add_track(cc.TrackType.video, "main")
    d.add_track(cc.TrackType.text, "text")
    d.add_segment(cc.VideoSegment(str(ASSETS / PHOTO), tr(0, 3)), "main")
    d.add_segment(cc.VideoSegment(str(ASSETS / VIDEO), tr(3, 3)), "main")
    d.add_segment(cc.TextSegment("SMOKE TEST 1", tr(0, 6)), "text")
    d.save()


def smoke_effects(folder):
    """본 작업에서 쓸 기능(마스크, 키프레임, 전환, 페이드)을 한 번씩 넣은 드래프트."""
    d = new_draft(folder, "smoke_2_effects")
    d.add_track(cc.TrackType.video, "main")
    d.add_track(cc.TrackType.video, "window")
    d.add_track(cc.TrackType.text, "text")

    # 배경 레이어 대용: 사진을 전체 화면으로 (본 작업에서는 어두운 잔디 사진)
    bg = cc.VideoSegment(str(ASSETS / PHOTO), tr(0, 8))
    d.add_segment(bg, "main")

    # 가운데 창 대용: 사진, 영상 두 클립에 디졸브 + 마스크(Feather) + 줌 키프레임 + 페이드
    a = cc.VideoSegment(
        str(ASSETS / PHOTO), tr(0, 4),
        clip_settings=cc.ClipSettings(scale_x=0.96, scale_y=0.96),
    )
    a.add_mask(cc.MaskType.矩形, size=0.4, rect_width=0.96, feather=30, round_corner=10)
    a.add_keyframe(cc.KeyframeProperty.uniform_scale, 0, 1.0)
    a.add_keyframe(cc.KeyframeProperty.uniform_scale, "4s", 1.1)
    a.add_fade("0.5s", "0.5s")
    a.add_transition(cc.TransitionType.叠化, duration="1s")

    b = cc.VideoSegment(
        str(ASSETS / VIDEO), tr(4, 4),
        clip_settings=cc.ClipSettings(scale_x=0.96, scale_y=0.96),
    )
    b.add_mask(cc.MaskType.矩形, size=0.4, rect_width=0.96)
    b.add_fade("0.5s", "0.5s")
    d.add_segment(a, "window")
    d.add_segment(b, "window")

    t = cc.TextSegment("SMOKE TEST 2", tr(0, 8), clip_settings=cc.ClipSettings(transform_y=0.5))
    t.add_animation(cc.TextIntro.渐显, "0.5s")
    d.add_segment(t, "text")
    d.save()


MEDIA_TOKEN = "__MEDIA_DIR__"
ROOT_TOKEN = "__DRAFT_ROOT__"

INSTALL_SH = """#!/bin/bash
# 맥에서 실행: 소재 폴더를 만들고, 드래프트의 경로를 이 맥에 맞게 바꿔서 CapCut 드래프트 폴더에 설치한다.
# 사용법: bash install.sh            (기본 CapCut 드래프트 폴더 사용)
#         bash install.sh "<드래프트 폴더 경로>"   (다른 위치일 때)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
MEDIA_DIR="$HOME/Movies/wedding_assets"
DRAFT_ROOT="${1:-$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft}"

if [ ! -d "$DRAFT_ROOT" ]; then
  echo "CapCut 드래프트 폴더를 찾을 수 없음: $DRAFT_ROOT"
  echo "CapCut을 한 번 실행해서 프로젝트를 하나 만든 뒤 다시 시도하거나, 경로를 인자로 넘겨주세요."
  exit 1
fi

mkdir -p "$MEDIA_DIR"
cp "$HERE"/assets/* "$MEDIA_DIR"/

for d in "$HERE"/drafts/*/; do
  name="$(basename "$d")"
  dst="$DRAFT_ROOT/$name"
  rm -rf "$dst"
  cp -R "$d" "$dst"
  sed -i '' -e "s|__MEDIA_DIR__|$MEDIA_DIR|g" -e "s|__DRAFT_ROOT__|$DRAFT_ROOT|g" "$dst"/*.json
  echo "설치됨: $dst"
done
echo "완료. CapCut을 완전히 종료(Cmd+Q)했다가 다시 실행해서 프로젝트 목록을 확인하세요."
"""


def finalize_meta(draft_dir, name, duration_us):
    """CapCut이 프로젝트 목록에 정상 표시하도록 draft_meta_info.json 의 빈 필드를 채운다."""
    f = draft_dir / "draft_meta_info.json"
    meta = json.loads(f.read_text(encoding="utf-8"))
    now_us = int(time.time() * 1_000_000)
    meta.update({
        "draft_name": name,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_duration": duration_us,
        "draft_root_path": ROOT_TOKEN,
        "draft_fold_path": f"{ROOT_TOKEN}/{name}",
    })
    f.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def tokenize_paths(draft_dir):
    local = str(ASSETS)
    for f in draft_dir.glob("*.json"):
        text = f.read_text(encoding="utf-8")
        f.write_text(text.replace(local, MEDIA_TOKEN), encoding="utf-8")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    pack = OUT / "smoke_test_pack"
    (pack / "drafts").mkdir(parents=True)
    (pack / "assets").mkdir()
    folder = cc.DraftFolder(str(pack / "drafts"))

    smoke_basic(folder)
    smoke_effects(folder)
    for name, dur in (("smoke_1_basic", 6_000_000), ("smoke_2_effects", 8_000_000)):
        d = pack / "drafts" / name
        tokenize_paths(d)
        finalize_meta(d, name, dur)
        print("created", d.name, sorted(p.name for p in d.iterdir()))

    for fn in (PHOTO, VIDEO):
        shutil.copy(ASSETS / fn, pack / "assets" / fn)
    (pack / "install.sh").write_text(INSTALL_SH, encoding="utf-8")
    zip_path = shutil.make_archive(str(OUT / "smoke_test_pack"), "zip", OUT, "smoke_test_pack")
    print("zip:", zip_path)


if __name__ == "__main__":
    main()
