# Thermal Target Tracker — Complete Documentation

Everything about this POC in one place: what it is, why it exists, how every part works, the exact settings, the results, the mistakes, the limits, and answers to the questions people ask.

---

## 0. How to use this document

- **Before a presentation:** read sections 1, 2, 3 and 12, then practise section 13 (question bank) out loud.
- **To understand the system:** read sections 6 and 7 with the portal open, using **Take the tour**.
- **To answer "what are the numbers?":** section 8.
- **To answer "what's wrong with it?":** sections 9 and 10.
- **What to do next:** section 15 (day-by-day plan).

---

## 1. The project in 30 seconds

**One line:** Other trackers tell you what they saw. Mine also tells you what it might have missed.

**Thirty-second version:** A drone's thermal camera AI marks people and vehicles for the operator. When conditions get bad — a fast turn, low thermal contrast, high altitude, blur — it quietly misses targets, and the screen simply looks empty. I built a tracker on real thermal drone data that follows moving people and vehicles, and that also reports its blind spots: where a target was last seen, which parts of the flight could not be trusted and why, and which parts of the ground need a second look. I measured whether those warnings match real losses.

**What it is not:** It is not a new detector or a new tracking algorithm. Those are existing tools. It is not tested on a real drone or on company footage yet.

---

## 2. The problem

### 2.1 How a camera drone finds targets
1. A thermal camera on the drone sees heat. People and engines are warmer than the ground, so they stand out.
2. An AI detector on the drone (or ground station) draws a box around each person or vehicle.
3. An operator watches the marked video, often for hours and often several feeds at once.

### 2.2 What goes wrong
The detector does not fail loudly. It just draws fewer boxes. Common causes:
- **Thermal crossover** — around dawn and dusk, ground and people reach similar temperatures, so people fade.
- **Fog, rain, humidity** — water absorbs infrared; the image flattens.
- **Hot spots** — fires or sun-heated roofs blow out the image; automatic brightness darkens everything else.
- **Sensor noise** — grain and stripes, worse on cheaper sensors.
- **Blur and fast turns** — wind, sharp turns or a moving gimbal smear the image.
- **Altitude** — from 130 m a person is only a few pixels wide.

### 2.3 Why it matters for military and security drones
- Missions happen at the worst times: night, dawn, dusk, bad weather.
- Drones fly high to stay safe, which makes targets tiny.
- In surveillance, a **missed person** is the dangerous mistake. A false alarm costs a second look; a miss can cost much more.
- An empty screen looks exactly like an empty area. The operator cannot tell "nobody is there" from "the camera couldn't see".

### 2.4 The question this POC answers
**Can a drone's tracker report when and where it was unreliable, and do those warnings match real losses?**

---

## 3. Is it new? What did I do? (Ownership, honestly)

### 3.1 What already exists
| Part | What it is | Who made it |
|---|---|---|
| YOLOv8 | Object detector | Ultralytics (open source, AGPL-3.0) |
| ByteTrack | Multi-object tracker | Zhang et al., 2022 (published method) |
| Optical flow, RANSAC homography, frame differencing | Classic computer-vision methods | OpenCV library |
| HIT-UAV | Thermal drone dataset | Harbin Institute of Technology, 2023 |
| Moving-target tracking as a product feature | Sold by drone makers | e.g. ideaForge advertises it |

### 3.2 What this project adds
- **The question:** treating "knowing when it's blind" as the goal, not only detection.
- **Blind-spot features:** ground-pinned last-seen markers, unreliable periods with causes, a flight reliability report, and a "searched vs actually seen" coverage map with a re-scan list.
- **Reliability checks designed for thermal drone video:** six checks, weakest wins, including altitude based on my measured detection rates.
- **Measurement:** recall and precision; detection by altitude and day/night; whether warnings match real losses; testing on frames never used for tuning.
- **Finding and fixing three mistakes** (section 9) and reporting honest numbers.

### 3.3 How the work was done
- I chose the problem, the direction and the decision rules.
- The code was written with help from an AI assistant (Claude). I am rebuilding the core steps myself and running my own experiments (section 15).
- **Say this openly.** A POC proves an idea works in a context; it does not need to invent new technology. Hiding AI help is the real risk.

### 3.4 How to say it in one breath
"The tracking uses published tools. My contribution is making the tracker report its own blind spots and measuring whether those warnings are right, on real thermal drone data."

---

## 4. Choosing the idea

### 4.1 Ideas considered
| Idea | Decision | Reason |
|---|---|---|
| Fog removal for daylight video | Dropped | Daylight camera; well researched; military drones rely on thermal |
| Flight-log anomaly detection | Dropped | Useful but not visual; harder to demonstrate |
| Navigation without GPS | Dropped | Needs hardware; too large for two months |
| Perception health monitor (single images) | Became part of this | The trust checks came from here |
| **Thermal moving-target tracking with blind-spot reporting** | **Chosen** | Thermal is what military drones use; competitors sell tracking; public labelled data; measurable; showable |

### 4.2 Decision rules I used
1. Relevant to military or security drones.
2. Doable in about two months.
3. Real public data available.
4. Results can be measured with numbers.
5. Can be shown in a short demo.

---

## 5. The data: HIT-UAV

### 5.1 Facts
| Item | Value |
|---|---|
| Full name | HIT-UAV: A high-altitude infrared thermal dataset for UAV-based object detection |
| From | Harbin Institute of Technology |
| Published | *Scientific Data* 10, 227 (2023) |
| Licence | CC BY 4.0 (free to use with credit) |
| Images | 2,898 thermal images, 640 × 512 pixels |
| Split | 2,029 train · 290 validation · 579 test |
| Altitude | 60 to 130 m |
| Camera angle | 30 to 90 degrees |
| Time | Day and night |
| Classes | Person, Car, Bicycle, Other vehicle (plus "DontCare", ignored) |
| Scenes | Schools, parking lots, roads, playgrounds |
| Videos | 5 sample flight videos, 7.5 frames per second |
| Link | https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset |

### 5.2 How to read a file name
`1_130_30_0_03807.jpg` → `1` = night (0 = day), `130` = altitude in metres, `30` = camera angle in degrees, then an index. The day/night code comes from the dataset's own `scenario.txt` (day, night). Video names like `60m-40_3.mov` give altitude and angle; they do not record day or night.

### 5.3 Test-set contents
579 images with 4,780 labelled targets. Most are people and cars; "other vehicle" is rare (12 in validation).

### 5.4 Limits of the data
- Civilian scenes (campus, roads), not military terrain or vehicles.
- Videos have no tracking labels (no answer key for IDs).
- No recorded weather per video; the bad conditions on still images are simulated.
- It is **not** ideaForge's data. ideaForge is a company that sells tracking.

---

## 6. System overview

### 6.1 The pipeline (per video frame)
1. **Detect** people and vehicles (YOLOv8 nano).
2. **Steady the video** (optical flow + RANSAC homography).
3. **Find what moved** (frame differencing → motion map).
4. **Track** with IDs (ByteTrack); drop tracks under 1 s.
5. **Moving or still** (movement over 1.5 s after removing drone motion).
6. **Reliability** (six checks, weakest wins).
7. **Blind spots** (last-seen markers, unreliable periods, flight report).
8. **Coverage map** (where on the ground the drone actually saw, and what to re-scan).
9. **Display extras** (colour palettes and the hottest spot; these don't change what the AI sees).

### 6.2 Which file does what
| Step | File | Language |
|---|---|---|
| Arrange dataset | `src/prepare_dataset.py` | Python |
| Train detector | `src/train_detector.py` | Python |
| Score detector | `src/eval_detector.py` | Python |
| Steps 1–4 on videos | `src/process.py` | Python |
| Step 5 | `src/post.py` | Python |
| Image checks | `src/thermal.js`, `src/trust_clip.js` | JavaScript |
| Steps 6–7 | `src/reliability.py` | Python |
| Step 8 + hottest spot | `src/coverage.py` | Python |
| Trust-score test on images | `src/trust_test.js` | JavaScript |
| Tracker settings | `src/thermal_track.yaml` | YAML |
| Portal | `docs/index.html` / `Thermal_Target_Tracker.html` | HTML + JavaScript |

Results are computed in advance and the portal plays them back in sync with the video.

### 6.3 Is there a backend?
No live backend or server. Everything heavy runs **beforehand** in Python on a laptop: the detector, alignment, tracking, reliability and the coverage map. Each flight's results are saved as one JSON file (boxes, IDs, moving/still, reliability, last-seen markers, report, coverage map) next to its video. The portal is plain HTML and JavaScript: it plays the video and draws the saved results on top, frame by frame. The colour palettes are the only image processing done live in the browser.

So if someone asks **"is it real-time?"**: *"Not yet. It runs offline on recorded flights. Running it live on a drone computer (for example a Jetson) is a next step, and I haven't measured that speed."*

**The full chain, start to end:**
`HIT-UAV images` → `prepare_dataset.py` → `train_detector.py` (YOLOv8n) → `eval_detector.py` (91% / 88%) → for each video: `process.py` (align, motion map, detect, ByteTrack) → `post.py` (moving or still) → `trust_clip.js` (image checks) → `reliability.py` (score, last-seen, report) → `coverage.py` (map, re-scan list, hottest spot) → one JSON per flight → portal (HTML + JavaScript).

---

## 7. Every step in detail

Each step: what it does, why, how (simply), the exact settings, where it fails, and the likely question.

### 7.1 Detector — YOLOv8 nano
- **What:** finds people, cars, bicycles and other vehicles; outputs a box, a class and a confidence (0–1) for each.
- **Why nano:** the smallest YOLO (about 3 million parameters). A drone's computer is small; speed matters.
- **How (simply):** the network looks at the whole image once, predicts boxes for each area, then merges overlapping boxes for the same object, keeping the most confident (non-maximum suppression).
- **Training:** started from a model pre-trained on everyday photos (COCO); fine-tuned on the 2,029 HIT-UAV training images; 8 epochs; image size 640; batch 16; on a laptop-class CPU (about 1.5 hours).
- **Validation after training:** precision 0.73, recall 0.79, mAP50 0.78, mAP50-95 0.49. Per class recall: person 0.87, car 0.94, bicycle 0.78, other vehicle 0.58 (only 12 examples).
- **Test results:** see section 8.1.
- **Settings in use:** confidence 0.25 for scoring images; 0.1 as tracker input (the tracker decides what to keep).
- **Fails when:** targets are tiny, low contrast, blurred; can mislabel blurred car parts as "bicycle".
- **Likely question:** *"Was it tested on images it trained on?"* — No. Train, validation and test sets are separate.

### 7.2 Steady the video — homography
- **What:** lines up each frame with the previous one so the ground stands still.
- **Why:** the drone moves, so otherwise every building and parked car seems to move.
- **How (simply):** pick sharp corner points, find where each moved in the next frame, then find the one shift-rotate-tilt rule most points agree with, ignoring wrong matches (RANSAC). Warp the previous frame with that rule.
- **Settings:** up to 600 corner points (minimum spacing 8 px); Lucas–Kanade optical flow, window 21 × 21, 3 pyramid levels; RANSAC error limit 2 px.
- **Typical values:** about 250–320 points matched per frame; drone shift from under 1 px per frame (steady) to about 26 px (fast turn).
- **Fails when:** fast turns (blur, fewer good matches), tall buildings (parallax — the flat-ground assumption breaks).
- **Likely question:** *"What is RANSAC?"* — A method that tries many small random groups of matches and keeps the answer most matches agree with, so a few wrong matches do not spoil it.

### 7.3 Find what moved — motion map
- **What:** a black-and-white image; white where something moved relative to the ground.
- **Why:** the detector knows *what* something is; the motion map knows *whether it moved*.
- **How:** blur both frames slightly, subtract the aligned previous frame from the current one, keep pixels that changed by more than 16 (on 0–255), clean up specks, ignore a 12 px border.
- **Settings:** blur 5 × 5; threshold 16; clean-up 3 × 3 opening, 5 × 5 dilation; motion spots kept if 60–4,000 px in area.
- **Unconfirmed motion:** white spots the detector did not confirm are shown as dashed green boxes ("Raw motion" button).
- **Fails when:** trees in wind, heat shimmer, alignment errors at edges.
- **Likely question:** *"Why not only the motion map?"* — It lights up leaves and shimmer too; the detector filters those out, and also finds people standing still.

### 7.4 Track — ByteTrack
- **What:** links boxes frame to frame so each target keeps one ID.
- **How (simply):** predict where each track will be (Kalman filter), match predictions with new boxes by overlap (IoU), give low-confidence boxes a second chance to match leftover tracks (the "Byte" idea), start new IDs for unmatched confident boxes, keep lost tracks for a while.
- **Settings (`thermal_track.yaml`):** high threshold 0.3, low 0.1, new-track threshold 0.4, memory 45 frames (about 6 s), match threshold 0.9.
- **Extra rule:** tracks shorter than 1 s are dropped as noise.
- **Fails when:** people walk close together (IDs swap), targets leave and re-enter view, blur.
- **Likely question:** *"Why 201 IDs on the running track?"* — Many people enter and leave the view over 2+ minutes, and IDs break when people overlap. Without an answer key the number of mistakes is not measured yet.

### 7.5 Moving or still
- **What:** decides whether each target is moving across the ground.
- **How:** take where the target was 1.5 s ago, carry that point forward through every frame's camera correction, compare with where it is now.
- **Rule:** moving if it travelled more than `max(6 px, half the box's smaller side) + 6% of the total drone shift in that window`; the decision must hold for 3 frames before it changes.
- **Speed shown:** pixels per second in the image (not metres; the camera's field of view is not published).
- **Why 1.5 s:** small box wobble does not add up over time; real movement does (see mistake 1, section 9).
- **Fails when:** very fast turns (a few parked cars can briefly flip to "moving"; the portal warns "turning fast, uncertain").

### 7.6 Reliability — six checks
Each check gives 0–100. The **weakest** sets the frame's reliability, because one serious problem is enough. Green ≥ 70, amber 40–69, red < 40.

| Check | Measures | Healthy → bad |
|---|---|---|
| Thermal contrast | How much small spots stand out from their surroundings | 0.016 → 0.001 |
| Sensor noise | Pixel-to-neighbour jumps; column stripes | noise 0.012 → 0.04; stripes 0.008 → 0.02 |
| Hot-spot saturation | Share of pixels at maximum brightness | 2% → 15% |
| Altitude | My measured daytime detection rate at that altitude | 90% → 60% found |
| Blur | Sharpness compared with this flight's own last 3 s | 85% → 55% of recent sharpness |
| Drone turn | How far the view shifted since the last frame | 6 px → 15 px |

- **Why blur is relative:** an absolute blur measure fired on sharp frames with straight lines (field edges). See mistake 2.
- **Why altitude uses daytime rates:** these videos don't record day or night, so the cautious choice is used.
- **Origin:** the contrast, noise and saturation checks were first built and tuned on still images (504 test cases), then reused for video.

### 7.7 Blind-spot reporting
- **Last-seen markers:** when a target followed for at least 2 s disappears away from the image edge (more than 24 px from it), a dashed circle stays at its last ground position, moved with the camera correction each frame, for up to 8 s. Orange = lost while reliability was below 70; grey = lost in good conditions.
- **Unreliable periods:** frames below 70, merged when gaps are under 1 s, kept if at least 0.5 s long; labelled by their most common cause.
- **Flight reliability report:** share of flight time reliable, list of unreliable periods (click to replay), list of targets lost in view (click to replay).

### 7.8 Searched vs actually seen (coverage map)
- **What:** a map of the ground the flight covered, coloured by how well each spot was actually seen, plus a re-scan list.
- **Why:** a commander asks "did we check that area?" The flight path says yes; the map says whether the camera could actually see there. "Flew over it" is not the same as "saw it".
- **How (simply):** line up each frame with the previous one (shift, rotation and scale), chain those so every frame has a place on one big map, and paint each frame's image there. For every spot on the map, count how many frames saw it and how reliable those frames were.
- **Colours:** green = in view for at least 0.5 s (4 frames) with reliability 70+; amber = in view at least 0.5 s but only with reliability 40–69; red = flown over but never in view long enough in usable conditions.
- **Re-scan list:** joined-up red patches become **priority 1** (never seen in usable conditions), amber patches **priority 2** (seen only in weak conditions). Patches under 1% of the flown area are ignored (thin edge slivers). Each comes with the time it was in view and the most common cause.
- **In the portal:** the white box shows the camera's current view moving over the map; the dashed line is the path so far; crosses mark lost targets. Clicking anywhere jumps the video to the best view of that spot.
- **Why shift + rotation + scale and not the full homography:** chaining hundreds of full homographies lets tiny tilt errors grow until the map explodes (one flight reached 21,000 px wide). The simpler model is less exact for tilted cameras but stays stable.
- **Settings:** `MIN_FRAMES = 4`, `MIN_AREA = 1%`, map at most 900 px on its longest side, a 3 px frame border skipped to avoid dark seams.
- **Fails when:** fast turns leave a visible seam; long flights drift; there is no GPS, so the map is not in metres. With the drone's GPS and camera angle, the same idea gives a real map.
- **Likely question:** *"Isn't this just a mosaic?"* — The stitching is a standard technique. What is new is colouring the ground by how reliably it was seen and turning that into a re-scan list.

### 7.9 Colour palettes and the hottest spot
- **Palettes:** White-hot (the original image), Black-hot (inverted) and Ironbow (the purple-orange-yellow look on commercial drone screens). Done in the browser with a 256-colour lookup table.
- **The AI never sees the colours.** It was trained on grayscale and always runs on the original image. Palettes only help the operator's eyes.
- **Hottest spot:** the brightest area of each frame after a 15 px blur (so a single noisy pixel can't win), shown as a yellow crosshair with its brightness out of 255.
- **Brightness is not temperature.** HIT-UAV videos are not radiometric (they don't store degrees per pixel), so it means "warmest compared with the rest of this frame". By day it is often a sun-heated roof or road.
- **Likely question:** *"Can it show temperature?"* — Not with this data. A radiometric camera (e.g. the kind on enterprise thermal drones) stores degrees per pixel; with that, the same marker could show °C and alert on a heat threshold.

---

## 8. Measurements and results

### 8.1 Detector on 579 unseen test images
| Confidence setting | Recall (targets found) | Precision (alarms correct) |
|---|---|---|
| 0.25 (used) | 91.1% of 4,780 | 87.8% of 4,958 alarms |
| 0.40 (stricter) | 84.6% | 94.7% |

Lower setting = catch more, more false alarms. For surveillance, catching more usually matters more.

### 8.2 Detection by altitude (same test set, no simulation)
| | 60 m | 70 m | 80 m | 90 m | 100 m | 110 m | 120 m | 130 m |
|---|---|---|---|---|---|---|---|---|
| Day | 94% | 87% | 94% | – | 85% | 76% | 96% | 73% |
| Night | 95% | 87% | 91% | 83% | 89% | 92% | 91% | 95% |

At 110–130 m: about 84% by day vs 93% at night. The trend is not smooth (scenes and image counts differ per altitude), so say "by day it tends to drop at height".

### 8.3 What bad conditions do to the detector (simulated on 24 real test frames)
Share of real targets still found, average:

| Condition | 25% | 50% | 75% | 100% strength |
|---|---|---|---|---|
| None (clean) | 90% | | | |
| Thermal crossover | 92% | 83% | 47% | 5% |
| Fog / rain | 86% | 76% | 41% | 10% |
| Sensor noise | 79% | 35% | 15% | 2% |
| Hot-spot | 76% | 60% | 39% | 17% |
| Shake / blur | 66% | 36% | 21% | 10% |

### 8.4 Does the image trust score catch failures? ("failure" = AI found under 40% of targets)
| Test | Cases | Failures caught (amber/red) | False "all clear" | Notes |
|---|---|---|---|---|
| Tuning frames (24) | 504 | 221 of 226 | 5 | Thresholds were tuned here, so optimistic |
| **New frames (24, never used for tuning)** | 504 | **205 of 209** | **4** | Correlation 0.55; over-cautious: only 13 of 24 untouched frames green; 58 cases red while the AI still found ≥ 80% |

### 8.5 Do video warnings match real losses?
Across the five flights, a "loss" = a target followed for ≥ 2 s vanishing away from the image edge.
- Unreliable periods: 17 losses in 3.3 target-minutes → about 5.2 per target-minute.
- Reliable periods: 109 losses in 38.4 target-minutes → about 2.8 per target-minute.
- **Ratio: about 1.8× more losses when the system said "unreliable".**
- Caveats: small sample; no answer key, so a loss could also be a real exit behind a building; most losses on the running track happen in good conditions (tracker ID breaks).

### 8.6 Per flight
| Flight | Length | Tracks | Reliable time | Unreliable periods | Lost in view (in bad conditions) |
|---|---|---|---|---|---|
| Walkers, 70 m, 90° | 32.8 s | 21 | 100% | none | 5 (0) |
| Running track, 60 m, 30° | 139.3 s | 201 | 97% | 2 blur, 3 fast turns | 102 (7) |
| Parking lot, 60 m, 40° | 28.9 s | 73 | 47% | low contrast 0–6.7 s; fast turns 12.9–17.5, 18.9–20.7, 24.0–25.9 s | 15 (8) |
| Roadside, 120 m, 30° | 28.8 s | 22 | 97% | 1 fast turn | 3 (1) |
| Open ground, 130 m, 60° | 34.5 s | 14 | 0% | altitude (daytime assumption) | 1 (1) |

### 8.7 Searched vs actually seen (coverage map)
Share of the ground each flight flew over:

| Flight | Seen reliably | Weak only | Not really seen | Re-scan list |
|---|---|---|---|---|
| Walkers, 70 m | 99.8% | 0% | 0.2% | none |
| Running track, 60 m | 99.5% | 0% | 0.5% | none |
| Parking lot, 60 m | 72.2% | 26.6% | 1.3% | A (priority 2): 26% of ground, low contrast, 0–5.6 s |
| Roadside, 120 m | 99.3% | 0% | 0.7% | none |
| Open ground, 130 m | 0% | 55.7% | 44.3% | A (priority 1): 43%, fast turn, 7.9–10.1 s · B (priority 2): 39%, altitude, 17.1–23.9 s · C (priority 2): 17%, fast turn, 0–3.9 s |

What this shows:
- **Parking lot:** the fast turns later in the flight did **not** create a red area, because that ground had already been seen well. Only the start, seen in low contrast, needs another look. The time-based report (47% reliable) and the ground-based map (72% seen reliably) answer different questions.
- **Open ground:** the drone flew over the whole arc, but 44% of it was never seen in usable conditions, mainly during the fast turn.
- Caveat: the map is stitched from video (no GPS), and the amber at 130 m depends on the daytime altitude assumption.

---

## 9. Mistakes found and fixed

### 9.1 65 parked cars marked "moving"
- **Seen:** in the parking-lot flight, 65 of 73 tracked cars showed as moving.
- **Cause:** a frame-to-frame rule (about half a pixel per frame) was too sensitive; in a fast turn the camera correction is imperfect and boxes wobble by a pixel or two.
- **Fix:** judge movement over 1.5 s with chained camera correction, a size-aware threshold, and a 3-frame hold.
- **Result:** 1 of 73.

### 9.2 Sharp frames marked "blurred"
- **Seen:** 353 frames of the running track flagged as blurred, but the drone was turning fast in only 14.
- **Cause:** the blur check looked for edges much stronger in one direction; a straight field edge looks like that too.
- **Fix:** compare sharpness with the same flight's last 3 s, and add a separate fast-turn check.

### 9.3 A result that looked better than it was
- **Seen:** losses in bad conditions looked 2.5× more frequent.
- **Cause:** during fast turns, blur made the detector create short fake "bicycle" tracks that then vanished, inflating losses in bad conditions.
- **Fix:** count only targets followed for at least 2 s.
- **Result:** honest ratio 1.8×.

**Lesson:** an impressive number can be wrong. Check results against the video before believing them.

---

## 10. Limitations (say these before anyone asks)
1. Tracking accuracy (ID switches, IDF1) is **not measured**: the videos have no answer key.
2. Bad conditions on still images are **simulated**; altitude and day/night are real.
3. Civilian scenes; no military terrain or vehicles.
4. The trust score is **over-cautious** (about half of normal frames not green).
5. Detector trained only 8 epochs on a CPU.
6. Results are computed in advance; **not run live** or on drone hardware.
7. Speeds are in pixels per second, not metres per second.
8. Videos don't record day or night; altitude check assumes daytime.
9. Small samples for the "1.8×" result.
10. The homography assumes flat ground; tall buildings cause small errors.
11. The coverage map is stitched from video, not GPS: not in metres, and fast turns can leave seams.
12. The hottest spot is brightness, not temperature; these videos are not radiometric.

---

## 11. The five flights — what each one shows
- **Walkers (70 m, straight down):** the clean case. A group walking; IDs stay; all green.
- **Running track (60 m):** many people for over 2 minutes; shows ID breaks even in good conditions — a tracker weakness, not a conditions problem.
- **Parking lot (60 m):** the best demo. Parked cars correctly still; low-contrast start (amber); fast turns (red, "uncertain"); orange last-seen circles; the flight report shows 47% reliable.
- **Roadside (120 m):** small targets; mostly reliable; one brief fast turn.
- **Open ground (130 m):** few, tiny targets; amber the whole flight because of altitude by daytime rates. Best coverage-map demo: 44% of the arc was flown over but never really seen.

---

## 12. How to demo and present

### 12.1 Portal walkthrough (about 2 minutes)
1. Press **Take the tour** once yourself before presenting, to learn the screen.
2. Open **Parking lot, fast turn**. Press Play.
3. Point to the **blue boxes**: parked cars correctly "not moving".
4. At about 13 s: the panel turns **red**, "Drone turning fast"; the chip says "moving/still uncertain".
5. At about 19 s: **orange dashed circles** — targets lost during bad conditions, pinned to the ground.
6. Scroll to the **Flight reliability report**: 47% reliable; click a red period to replay it.
7. Open **Open ground at 130 m** and scroll to **Searched vs actually seen**: the drone flew the whole arc, but area A (the fast turn) was never really seen. Click A in the re-scan list to replay it.
8. Scroll to **Evidence**: read the four numbers, each with its caveat.

### 12.2 Five-minute presentation
1. **Problem (30 s):** an empty screen looks the same as a blind camera.
2. **Demo (2 min):** as above.
3. **Evidence (1 min):** 91% / 88%; day vs night at height; 205 of 209 on new frames; 1.8×.
4. **What's new, what's not (30 s):** section 3.4.
5. **Limits and next steps (30 s):** tracking accuracy and over-caution next.
6. **Ask (30 s):** is this useful, and what real footage could it be tested on?

### 12.3 Backup
Keep a 2-minute screen recording of the demo and screenshots offline, in case a laptop blocks the file.

---

## 13. Question bank

### The idea
- **What does it do, in one line?** Tracks moving people and vehicles in thermal drone video and reports where and when it could not be trusted.
- **What's new?** The blind-spot reporting and the measurement of whether its warnings match real losses. Detection and tracking are existing tools.
- **ideaForge already sells tracking — why build this?** Buyers compare tracking features. Mine adds knowing when tracking is unreliable, which I did not see advertised.
- **Who would use it?** Surveillance, border watch, search and rescue — anywhere a missed person is costly.
- **Why thermal and not normal camera?** Military drones rely on thermal at night; people and engines stand out by heat.
- **Did you invent the algorithm?** No. I used YOLO, ByteTrack and OpenCV, and built the reliability layer and the tests.
- **Did you write the code yourself?** I wrote it with help from an AI assistant, and I'm rebuilding the core steps and running my own experiments.

### The data
- **What dataset?** HIT-UAV, a public thermal drone dataset from Harbin Institute of Technology, 2023.
- **How big?** 2,898 images (2,029 / 290 / 579), 4,780 labelled targets in the test set, five flight videos.
- **Is it allowed to use?** Yes, CC BY 4.0 with credit.
- **It's civilian — does it apply to military drones?** The checks measure the image and flight, not what the target is. Mission footage is the real test.
- **How do you know day or night?** From the file name code (0 day, 1 night), defined in the dataset's scenario file.

### Detection
- **What is YOLO?** An AI that finds objects in an image in one pass and outputs boxes with class and confidence.
- **Why nano?** Small and fast enough for drone hardware.
- **What is recall? Precision?** Recall: share of real targets found. Precision: share of alarms that were real.
- **Your numbers?** 91% recall, 88% precision on 579 unseen images at confidence 0.25.
- **Why not higher precision?** At 0.40 it's 95% precision but recall drops to 85%. For surveillance I prefer catching more.
- **How long did training take?** 8 epochs, about 1.5 hours on a laptop-class CPU.

### Stabilising and motion
- **Why line up frames?** The drone moves, so everything appears to move until the ground is held still.
- **What is a homography?** A rule that shifts, rotates, stretches and tilts one image onto another of the same flat scene.
- **What is RANSAC?** It finds the rule most point matches agree with and ignores wrong matches.
- **What is the motion map?** White where brightness changed after alignment, meaning real movement.
- **What breaks it?** Fast turns, tall buildings, trees in wind.

### Tracking
- **What does ByteTrack do?** Links boxes across frames so each target keeps one ID, and gives faint boxes a second chance to match.
- **What is an ID switch?** A target wrongly gets a new number or swaps numbers with another.
- **What is IDF1?** How consistently each real target kept one correct ID, 0–100.
- **Your tracking accuracy?** Not measured yet — no answer key. That's my next step.
- **How do you decide moving vs still?** Movement over 1.5 s after removing drone motion, above a size-aware threshold, held for 3 frames.

### Reliability and blind spots
- **How is the trust score calculated?** Six checks, each 0–100; the weakest sets the score. Green ≥ 70, amber 40–69, red < 40.
- **Why the weakest and not the average?** One serious problem — e.g. a fast turn — is enough to make the output unreliable; an average would hide it.
- **How do you know the warnings mean anything?** On new frames, 205 of 209 AI failures were flagged. In videos, targets were lost about 1.8× more often during flagged periods.
- **What's the weakness of the trust score?** Over-cautious: about half of normal frames aren't green. Reducing false alarms is my next task.
- **What is a last-seen marker?** When a followed target vanishes mid-view, a circle stays at its last ground position for up to 8 s.
- **Why pin it to the ground?** Because the drone moves; the marker moves with the camera correction so it stays over the same spot.

### Coverage map, colours and hottest spot
- **What is the coverage map?** A map of the ground the drone flew over, coloured by how reliably each spot was seen, with a list of areas to re-scan.
- **Why does it matter?** "The drone flew over it" is not the same as "we saw it". It tells the team where to look again, and why.
- **How is it made?** Frames are lined up (shift, rotation, scale), chained onto one map, and each spot is coloured by how long and how reliably it was in view.
- **Is it in metres?** No; there is no GPS in these clips. With the drone's GPS it would be.
- **Is the hottest spot a temperature?** No, brightness. The videos don't store degrees.
- **Do the colours help the AI?** No. Display only; the AI sees the original grayscale image.
- **Can it detect animals?** Not now: HIT-UAV has 4 classes. Adding animals means retraining with labelled thermal animal data (e.g. BIRDSAI), which is a next step.

### Results and honesty
- **What went wrong along the way?** Section 9: parked cars as moving; a blur check fooled by straight lines; an inflated result from fake tracks.
- **What is not proven?** Section 10.
- **Is it real-time?** Not shown. Results were computed in advance; the next step is measuring speed on a drone computer.
- **Can it run on a drone?** The image checks are cheap and the detector is the smallest YOLO, but it is not tested on drone hardware.
- **What would you do with more time?** Measure tracking accuracy, reduce false alarms, test on real mission footage, test speed on a Jetson.

---

## 14. Glossary
| Term | Meaning |
|---|---|
| Thermal / infrared camera | Sees heat instead of light |
| Thermal crossover | Ground and targets at similar temperature; targets fade |
| Detector | AI that finds objects and draws boxes |
| YOLO | "You Only Look Once" — a fast detector family |
| Confidence | How sure the detector is, 0–1 |
| Non-maximum suppression | Merging overlapping boxes for the same object |
| Epoch | One full pass over the training images |
| Recall | Share of real targets found |
| Precision | Share of alarms that were real |
| mAP | A standard detection score averaging precision over recall levels |
| Homography | Rule that lines up two images of a flat scene |
| Optical flow | How points move between frames |
| RANSAC | Robust fitting that ignores wrong matches |
| Frame differencing | Subtracting frames to find change |
| Tracker | Keeps one ID per target across frames |
| ByteTrack | A published tracker that also uses low-confidence boxes |
| Kalman filter | Predicts where a target will be next |
| IoU | Overlap between two boxes (intersection over union) |
| ID switch | A target wrongly changes ID |
| IDF1 / MOTA | Standard tracking scores |
| Hysteresis | Requiring a change to hold for a few frames before switching |
| Ground station (GCS) | The operator's screen and controls |
| Parallax | Tall objects shift differently from the ground when the camera moves |
| Coverage map | Map of the ground covered, coloured by how reliably each spot was seen |
| Mosaic / stitching | Joining many frames into one big picture of the ground |
| Similarity transform | Shift + rotation + scale between two images (simpler than a homography) |
| Radiometric camera | Thermal camera that stores the temperature of each pixel |
| Colour palette (Ironbow, white-hot, black-hot) | Ways of colouring a grayscale thermal image for the eye |

---

## 15. Your plan from tomorrow

### Week 1 — make it yours and safe
- **Day 1:** Push the repository to GitHub; turn on Pages. Ask your mentor: does Raphe already have tracking, and is sharing this personal project fine?
- **Day 2:** Read sections 1–5. Take the portal tour twice.
- **Day 3:** Read sections 6–7 with the portal open. For each step, find it on screen.
- **Day 4:** Read sections 8–11. Write the four evidence numbers from memory.
- **Day 5:** Practise section 13 out loud; pass the quiz 8/8.
- **Day 6–7:** Install Python and Node on your Mac; run README steps 1 and 3 (dataset, detector score). Check you get 91% / 88%.

### Week 2 — rebuild the core
- Run `process.py`, `post.py`, `reliability.py` on one clip. Compare with the portal's numbers.
- Change one setting (e.g. motion threshold 16 → 20) and see what changes. Write it down.

### Weeks 3–4 — your own contribution
- **Task A, reduce false alarms:** in `thermal.js`, adjust the contrast check thresholds; re-run the trust test on the new frames; aim to keep failures caught ≥ 200 of 209 while raising green normal frames above 13 of 24. Record before/after.
- **Task B, tracking accuracy:** label about 150 frames of the Walkers clip (free tool: CVAT), then count ID switches and missed targets.
- **Coverage map check:** change `MIN_FRAMES` from 4 to 8 (1 s) in `coverage.py`, re-run it, and write down how the green share and re-scan list change. Be ready to explain why you chose your value.
- Commit each change to GitHub with a clear message.

### Week 5 — update results
- Put your new numbers into the portal, README and this document.

### Week 6 — presentation
- 5 slides; 2-minute backup recording; rehearse twice with family; present to your mentor.

### Week 7 — present and ask
- Present to your mentor, then Nitin sir if your mentor agrees. Ask what real footage it could be tested on.

---

## 16. Where to change things
| What | File | Setting |
|---|---|---|
| Trust thresholds | `src/thermal.js` | `lin(value, good, bad)` in `CHECKS` |
| Moving rule | `src/post.py` | `WINDOW_S`, `tol`, `HYST` |
| Shortest track | `src/post.py` | `MIN_TRACK_S` |
| Tracker | `src/thermal_track.yaml` | `track_buffer`, `match_thresh` |
| Blur and turn checks | `src/reliability.py` | `lin(...)` for `blur`, `turn` |
| Last-seen rules | `src/reliability.py` | `GHOST_S`, `EDGE`, 2 s minimum |
| Detector confidence | `src/process.py` | `conf=` |
| Coverage map | `src/coverage.py` | `MIN_FRAMES`, `MIN_AREA`, `MAP_MAX` |

---

## 17. Sources
- HIT-UAV dataset: https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset — Suo et al., *Scientific Data* 10, 227 (2023).
- HIT-UAV paper (arXiv): https://arxiv.org/abs/2204.03245
- BIRDSAI (thermal tracking dataset for next steps): Bondi et al., WACV 2020.
- ideaForge defence solutions (competitor features): https://us.ideaforgetech.com/defense-solutions/
- Ultralytics YOLOv8 (AGPL-3.0): https://github.com/ultralytics/ultralytics
- ByteTrack: Zhang et al., "ByteTrack: Multi-Object Tracking by Associating Every Detection Box", ECCV 2022.
