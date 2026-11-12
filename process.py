"""Moving-target detection + tracking on HIT-UAV thermal videos.

For every frame:
  1. Camera-motion compensation: track corner points from the previous frame (Lucas-Kanade optical flow),
     fit a homography with RANSAC, warp the previous frame onto the current one.
  2. Motion map: absolute difference of the aligned frames, thresholded and cleaned -> pixels that really moved.
  3. Detection + tracking: thermal YOLOv8n (trained on HIT-UAV) + ByteTrack keeps one ID per target.
  4. Moving or still: for each track, ground-relative speed = distance between its centre now and where its previous
     centre lands after the camera-motion correction; smoothed over ~1 s. Plus share of the box that the motion map lit up.
Outputs: H.264 video, a small motion-map video, and a JSON of per-frame results for the portal.
"""
import json, os, subprocess, sys, math
import numpy as np, cv2
from ultralytics import YOLO

SRC = 'data/HIT-UAV-Infrared-Thermal-Dataset/video_sample'
OUT = 'out'
MODEL = 'model/hituav_yolov8n.pt'
NAMES = ['person', 'car', 'bicycle', 'other vehicle']
os.makedirs(OUT, exist_ok=True)

def homography(prev, cur):
    pts = cv2.goodFeaturesToTrack(prev, maxCorners=600, qualityLevel=0.01, minDistance=8, blockSize=7)
    if pts is None or len(pts) < 12: return np.eye(3), 0
    nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, winSize=(21, 21), maxLevel=3)
    good0, good1 = pts[st.ravel() == 1], nxt[st.ravel() == 1]
    if len(good0) < 12: return np.eye(3), 0
    H, inl = cv2.findHomography(good0, good1, cv2.RANSAC, 2.0)
    if H is None: return np.eye(3), 0
    return H, int(inl.sum())

def project(H, x, y):
    v = H @ np.array([x, y, 1.0]); return v[0] / v[2], v[1] / v[2]

def run(path, max_frames=None):
    name = os.path.splitext(os.path.basename(path))[0]
    alt, angle = int(name.split('m-')[0]), int(name.split('-')[1].split('_')[0])
    cap = cv2.VideoCapture(path); fps = cap.get(cv2.CAP_PROP_FPS) or 7.5
    model = YOLO(MODEL)
    W, H0 = int(cap.get(3)), int(cap.get(4))
    mask_path = f'{OUT}/{name}_motion_raw.avi'
    mw = cv2.VideoWriter(mask_path, cv2.VideoWriter_fourcc(*'MJPG'), fps, (W // 2, H0 // 2), isColor=False)
    prev_gray, prev_centres, speeds = None, {}, {}
    frames, tracks_summary, i = [], {}, 0
    while True:
        ok, frame = cap.read()
        if not ok or (max_frames and i >= max_frames): break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        g = cv2.GaussianBlur(gray, (5, 5), 0)
        if prev_gray is None:
            Hm, inliers, motion = np.eye(3), 0, np.zeros_like(gray)
        else:
            Hm, inliers = homography(prev_gray, g)
            warped = cv2.warpPerspective(prev_gray, Hm, (W, H0), borderMode=cv2.BORDER_REPLICATE)
            diff = cv2.absdiff(g, warped)
            _, motion = cv2.threshold(diff, 16, 255, cv2.THRESH_BINARY)
            motion = cv2.morphologyEx(motion, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            motion = cv2.dilate(motion, np.ones((5, 5), np.uint8))
            edge = 12; motion[:edge] = 0; motion[-edge:] = 0; motion[:, :edge] = 0; motion[:, -edge:] = 0
        # camera motion for the frame: how far the image centre moved (pixels)
        cx, cy = project(Hm, W / 2, H0 / 2); cam = math.hypot(cx - W / 2, cy - H0 / 2)
        mw.write(cv2.resize(motion, (W // 2, H0 // 2), interpolation=cv2.INTER_AREA))
        # detection + tracking
        r = model.track(frame, persist=True, tracker='thermal_track.yaml', conf=0.1, iou=0.5, imgsz=640, verbose=False, device='cpu')[0]
        rows = []
        if r.boxes is not None and r.boxes.id is not None:
            for (x1, y1, x2, y2), tid, c, cf in zip(r.boxes.xyxy.numpy(), r.boxes.id.numpy().astype(int), r.boxes.cls.numpy().astype(int), r.boxes.conf.numpy()):
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                spd = 0.0
                if tid in prev_centres:
                    px, py = project(Hm, *prev_centres[tid]); spd = math.hypot(mx - px, my - py)
                s = speeds.get(tid, spd); s = 0.75 * s + 0.25 * spd; speeds[tid] = s
                prev_centres[tid] = (mx, my)
                bx1, by1, bx2, by2 = [int(max(0, v)) for v in (x1, y1, x2, y2)]
                lit = float((motion[by1:by2 + 1, bx1:bx2 + 1] > 0).mean()) if by2 > by1 and bx2 > bx1 else 0.0
                moving = 1 if (s > 0.55 or (lit > 0.25 and s > 0.3)) else 0
                rows.append([int(tid), int(c), round(float(x1), 1), round(float(y1), 1), round(float(x2 - x1), 1), round(float(y2 - y1), 1),
                             round(float(cf), 2), moving, round(s * fps, 1)])
                t = tracks_summary.setdefault(int(tid), {"id": int(tid), "cls": int(c), "first": i, "last": i, "moving": 0, "frames": 0, "dist": 0.0})
                t["last"] = i; t["frames"] += 1; t["moving"] += moving; t["dist"] += spd
        # motion blobs not explained by any detection ("something moved, AI not sure what")
        blobs = []
        if prev_gray is not None:
            n, lab, st, _ = cv2.connectedComponentsWithStats(motion)
            for k in range(1, n):
                x, y, w, h, a = st[k]
                if a < 60 or a > 4000: continue
                if any(not (x + w < b[2] or x > b[2] + b[4] or y + h < b[3] or y > b[3] + b[5]) for b in rows): continue
                blobs.append([int(x), int(y), int(w), int(h)])
        frames.append({"cam": round(cam, 2), "inl": inliers, "t": rows, "b": blobs[:12]})
        prev_gray = g; i += 1
        if i % 100 == 0: print(name, i, flush=True)
    cap.release(); mw.release()
    # encode browser videos (H.264)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-frames:v', str(i), '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', f'{OUT}/{name}.mp4'], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', mask_path, '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '30',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', f'{OUT}/{name}_motion.mp4'], check=True)
    os.remove(mask_path)
    tl = sorted(tracks_summary.values(), key=lambda t: t["first"])
    for t in tl: t["dist"] = round(t["dist"], 1)
    meta = {"name": name, "alt": alt, "angle": angle, "fps": fps, "w": W, "h": H0, "n": i, "frames": frames, "tracks": tl}
    json.dump(meta, open(f'{OUT}/{name}.json', 'w'), separators=(',', ':'))
    mv = sum(1 for t in tl if t["moving"] / max(1, t["frames"]) > 0.3)
    print(f'{name}: {i} frames, {len(tl)} tracks, {mv} mostly moving, mean camera motion {np.mean([f["cam"] for f in frames]):.1f}px')

if __name__ == '__main__':
    files = sys.argv[1:] or sorted(os.listdir(SRC))
    for f in files:
        run(os.path.join(SRC, f) if not f.startswith('/') else f)
