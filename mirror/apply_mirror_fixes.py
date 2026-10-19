#!/usr/bin/env python3
"""
apply_mirror_fixes.py — patches face_recognize.py and gesture_engine.py.

Run it from the mirror folder (next to those files and loopback_capture.py):

    python apply_mirror_fixes.py

Safe to run more than once. Each file is backed up to <name>.bak first, and is
restored from that backup if the patched result does not compile.
"""
import py_compile
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

FALLBACK = '''    # OpenCV's V4L2 backend can refuse the Pi's v4l2loopback device even though
    # ffmpeg reads it fine, so fall back to reading it through ffmpeg.
    if sys.platform != 'win32' and isinstance(target, str) and target.startswith('/dev/video'):
        try:
            from loopback_capture import FFmpegPipeCapture
            cap = FFmpegPipeCapture(target)
            if cap.isOpened():
                print(f"[CAMERA] OpenCV could not open {target}; reading it through ffmpeg instead.", flush=True)
                return cap
            cap.release()
        except Exception as e:
            print(f"[CAMERA] ffmpeg fallback failed: {e}", flush=True)

    return None
'''

TAIL_OLD = '''    # Try integer index with default backend
    if isinstance(idx, int):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            return cap
        cap.release()

    return None
'''

OPEN_CAMERA_NEW = '''def open_camera(rpi_mode: bool, camera_id: int) -> cv2.VideoCapture:
    if rpi_mode:
        # The loopback number is chosen by start_smart_mirror.sh. On a Pi 5 the
        # PiSP ISP owns /dev/video20-35, so it must not be 20.
        target = os.environ.get("MIRROR_LOOPBACK_DEV", "/dev/video42")
    else:
        target = camera_id
'''


def add_fallback(src, report):
    if "FFmpegPipeCapture" in src:
        report.append("ffmpeg fallback: already present")
        return src
    if TAIL_OLD not in src:
        report.append("ffmpeg fallback: !! end of _try_open_capture not found, skipped")
        return src
    report.append("ffmpeg fallback: added")
    return src.replace(TAIL_OLD, TAIL_OLD[:-len("    return None\n")] + FALLBACK, 1)


def patch_face(src, report):
    pat = re.compile(r"def open_camera\(rpi_mode: bool, camera_id: int\) -> cv2\.VideoCapture:\n"
                     r".*?(?=\n    mode_str = )", re.DOTALL)
    if pat.search(src):
        src = pat.sub(lambda m: OPEN_CAMERA_NEW, src, count=1)
        report.append("open_camera(): rewritten (indentation + desktop branch)")
    else:
        report.append("open_camera(): !! not found, skipped")
    return add_fallback(src, report)


def patch_gesture(src, report):
    old = 'RPI_CAMERA = "/dev/video20"'
    if old in src:
        src = src.replace(old, 'RPI_CAMERA = os.environ.get("MIRROR_LOOPBACK_DEV", "/dev/video42")', 1)
        report.append("RPI_CAMERA: now reads MIRROR_LOOPBACK_DEV")

    old_block = ('        if os.path.exists("/dev/video20"):\n'
                 '            camera = "/dev/video20"\n'
                 '        elif os.path.exists("/dev/video10"):\n'
                 '            camera = "/dev/video10"\n'
                 '        else:\n'
                 '            camera = RPI_CAMERA\n')
    if old_block in src:
        src = src.replace(old_block, '        camera = RPI_CAMERA\n', 1)
        report.append("parse_args(): removed video20/video10 guessing")

    old_set = ('                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  480)\n'
               '                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)\n'
               '                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)\n'
               '                cap.set(cv2.CAP_PROP_FPS, 30)\n')
    new_set = ('                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)\n'
               '                if not is_linux_loopback:      # the loopback has a fixed size\n'
               '                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  480)\n'
               '                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)\n'
               '                    cap.set(cv2.CAP_PROP_FPS, 30)\n')
    if old_set in src:
        src = src.replace(old_set, new_set, 1)
        report.append("run(): no size/fps requests on the loopback")

    return add_fallback(src, report)


def apply(name, patcher):
    path = HERE / name
    if not path.exists():
        print(f"{name}: not found next to this script — skipped")
        return False
    original = path.read_text(encoding="utf-8")
    report = []
    patched = patcher(original, report)
    print(f"{name}:")
    for line in report:
        print("   -", line)

    if patched == original:
        print("   (no changes needed)")
        return True

    shutil.copyfile(path, str(path) + ".bak")
    path.write_text(patched, encoding="utf-8")
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copyfile(str(path) + ".bak", path)
        print(f"   !! patched file did not compile, restored the original:\n{e}")
        return False
    print("   compiled OK")
    return True


def main():
    if not (HERE / "loopback_capture.py").exists():
        print("loopback_capture.py must be in the same folder — copy it here first.")
        return 1
    ok = apply("face_recognize.py", patch_face)
    ok = apply("gesture_engine.py", patch_gesture) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
