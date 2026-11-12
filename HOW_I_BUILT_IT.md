# How I built the Thermal Target Tracker

## In one line
Other trackers tell you what they saw. This one also tells you what it might have missed, and where to look again — and I measured whether those warnings are real.

## 1. The question I started with
Drones used for surveillance rely on a camera AI to point out people and vehicles. When conditions get bad — a fast turn, low thermal contrast, high altitude, blur — the AI quietly misses targets, and the screen just looks empty. An operator cannot tell "nobody is there" from "the camera couldn't see". My question: **can a drone's tracker report when and where it was unreliable, and do those warnings match real losses?**

## 2. Ideas I considered, and why I chose this one
| Idea | Why I dropped it or kept it |
|---|---|
| Clearing fog from daylight video | Daylight camera, heavily researched already, and military drones rely on thermal at night |
| Flight-log anomaly detection | Useful, but not visual and harder to show |
| Navigation without GPS | Very relevant, but needs hardware and is too big for two months |
| **Thermal moving-target tracking** | **Kept:** thermal is what military drones use; competitors (e.g. ideaForge) advertise tracking; public labelled data exists; results can be measured |

My decision rules: relevant to military drones, doable in about two months, real public data, measurable, and something I can show.

## 3. The data: HIT-UAV
A public research dataset from the Harbin Institute of Technology, published in *Scientific Data* (2023), free to use with credit (CC BY 4.0).
- 2,898 thermal (infrared) drone images, 640 × 512 pixels, with every person, car, bicycle and other vehicle boxed by hand.
- Flown at 60 to 130 m, camera angle 30 to 90°, day and night — written into each file name.
- Split into 2,029 training, 290 validation and 579 test images.
- Five sample flight videos (7.5 frames per second), used for the tracking demo.
It is not ideaForge's data; ideaForge is a competitor that sells tracking in its drones.

## 4. What I built, step by step, and why each choice
1. **Detector.** Trained YOLOv8 *nano* (the smallest YOLO, about 3 million parameters) on the 2,029 training images. Why nano: a drone's computer is small. Result on 579 unseen test images: found 91% of 4,780 real targets; 88% of its alarms were correct.
2. **Steady the video.** Track a few hundred corner points between frames and fit a homography with RANSAC, so the ground stands still. Why: the drone moves, so otherwise everything looks like it moves.
3. **Find what moved.** Subtract the aligned frames to get a motion map. Why: the detector knows *what* something is; the motion map knows *whether it moved*.
4. **Follow with IDs.** ByteTrack links detections frame to frame. Tracks shorter than 1 s are dropped as noise.
5. **Moving or still.** A target is "moving" if, after removing the drone's motion, it travelled more than about 6 px (or half its size) in 1.5 s, held for 3 frames.
6. **Reliability per frame.** Six checks, each 0–100, weakest wins: thermal contrast, sensor noise, hot-spot saturation, altitude (from my measured detection rates), blur compared with the last 3 s, and drone turn rate. Green ≥ 70, amber 40–69, red < 40.
7. **Blind-spot reporting (the new part).** Last-seen markers pinned to the ground when a followed target disappears; unreliable periods with their cause; a flight reliability report.
8. **Searched vs actually seen.** Chain the frames onto one map of the ground and colour each spot by how long and how reliably it was in view; turn badly seen patches into a re-scan list. Why: "the drone flew over it" is not the same as "we saw it".
9. **Display extras.** White-hot, black-hot and ironbow palettes, and the hottest spot per frame. Display only: the AI always sees the grayscale image, and brightness is not temperature.

## 5. Mistakes I found and fixed
1. **65 parked cars marked "moving".** In a fast turn, small alignment errors and box wobble fooled a frame-to-frame rule. Fix: judge movement over 1.5 s. Result: 1 of 73.
2. **Sharp frames marked "blurred".** The blur check reacted to straight lines such as field edges. Fix: compare blur with the same flight's last 3 s, plus a separate fast-turn check.
3. **An inflated result.** During fast turns blur created short fake "bicycle" tracks, which made losses in bad conditions look 2.5× more common. Fix: only count targets followed for ≥ 2 s. Honest result: 1.8×.
Lesson: a number that looks good can be wrong; check it against the video.

## 6. Results, with caveats
| Result | Caveat |
|---|---|
| Detector: 91% of targets found, 88% of alarms correct | Single images, not tracking |
| By day, detection falls to about 84% at 110–130 m; at night about 93% | Different scenes per altitude; trend not perfectly smooth |
| Targets lost 1.8× more often per target-minute when the system said "unreliable" | Five clips, 17 losses in bad conditions; no tracking answer key |
| Image trust score caught 205 of 209 AI failures on 24 frames it was never tuned on, 4 false "all clear" | Bad conditions simulated; over-cautious — only 13 of 24 normal frames showed green |
| 130 m flight: 44% of the ground flown over was never seen in usable conditions; parking lot: 72% seen reliably, 26% needs a second look | Map stitched from video (no GPS); altitude assumes daytime |

## 7. What is mine, what is existing, what is assisted
| Part | Source |
|---|---|
| YOLO, ByteTrack, OpenCV methods | Existing published tools |
| HIT-UAV data | Existing public dataset |
| Problem framing, choice of idea, decision rules | Mine |
| Code | Written with help from an AI assistant; I am rebuilding the core myself |
| Checking results against the video, the three fixes, the honest numbers | Done during the work; I can explain each |
| Next experiments (below) | Mine to do |
Be open about this split. A POC shows that an idea works in our context; it does not have to invent new technology.

## 8. What it does not prove yet, and my next steps
1. **Reduce false alarms** of the trust score without missing failures — change thresholds in `thermal.js`, re-test, report before and after.
2. **Measure tracking accuracy:** label about 150 frames of the Walkers clip (e.g. with CVAT), then count ID switches and IDF1.
3. **Test on a tracking dataset with an answer key** (BIRDSAI).
4. **Test on Raphe's own footage** — only with permission.
5. **Measure speed on a drone-class computer** (e.g. NVIDIA Jetson).

## 9. How I present it (5 minutes)
1. Problem (30 s): an empty screen looks the same as a blind camera.
2. Demo (2 min): Parking lot clip — tracking, the red fast-turn warning, last-seen markers, then the flight report.
3. Evidence (1 min): the four numbers, each with its caveat.
4. What's new and what's not (30 s): tracking is standard; blind-spot reporting and the measurements are my contribution.
5. Ask (1 min): is this useful for our surveillance missions, and can I test it on our footage?
