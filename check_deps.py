import shutil
import sys

def check():
    missing = []
    
    # Check cv2
    try:
        import cv2
        print("cv2: OK")
    except ImportError:
        print("cv2: MISSING")
        missing.append("opencv-python")

    # Check PIL
    try:
        import PIL
        from PIL import Image, ImageTk
        print("PIL: OK")
    except ImportError:
        print("PIL: MISSING")
        missing.append("Pillow")

    # Check FFmpeg
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        print(f"ffmpeg: OK ({ffmpeg})")
    else:
        print("ffmpeg: MISSING")
        missing.append("ffmpeg")

    if missing:
        print(f"MISSING_DEPS: {','.join(missing)}")
    else:
        print("ALL_OK")

if __name__ == "__main__":
    check()
