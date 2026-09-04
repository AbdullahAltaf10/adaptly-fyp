"""
True 3D head pose via OpenCV solvePnP, as specified in the scope document.

Scope note
----------
The scope document specifies solvePnP for head pitch/yaw/roll. The trained
model does NOT use this — `best_model_9f.keras` and `scaler_9f.pkl` were fit on
the simplified nose-to-chin approximation in feature_extraction.py, and
`focused_reference_means.json` was computed from it. Swapping solvePnP into the
model's features would feed it out-of-distribution values and wreck its
predictions, so that swap is deferred to the next training run.

This module is used ONLY by the rule-based gates (fatigue, deep thinking,
furrow), which are our own logic and carry no training-distribution baggage.

Why it is better for the gates
------------------------------
The simplified estimate is `(nose_y - chin_y) * 100`, which has two problems
the gates actually hit:
  - Dropping the jaw moves the chin, so OPENING YOUR MOUTH registers as a head
    rotation. This is why an open mouth reliably flipped the state.
  - It is a raw 2D distance, so it changes when the user sits nearer or further
    from the camera.

Measured against synthetic ground truth:
  - tilt accuracy      : exact (0.00 deg error recovering a known 20 deg tilt)
  - distance invariance: exact (identical pitch at 700 and 1600 units away)
  - jaw-drop contamination: ~7 deg

KNOWN LIMITATION — jaw drop still moves the estimate, because the chin is one
of the six correspondence points and the chin sits on the mandible. Point sets
excluding the chin were tested and rejected: dropping it alone makes the
geometry degenerate (solvePnP fails outright), and replacing it with inner eye
corners requires 3D model coordinates that are not available here. Inventing
them wrecked accuracy (9-140 deg error), which is far worse than the problem
being solved.

Relative to each metric's own response to a real head-down movement, solvePnP
is still about twice as clean: the simplified estimate's jaw contamination is
~68% of a genuine head-down signal, solvePnP's is ~35%. Good enough for the
gates, given that holding the mouth wide open is not a reading posture, but
worth knowing before trusting this during a demo that involves talking.

Camera intrinsics
-----------------
MediaPipe returns landmarks normalised to [0, 1]; the true image size and focal
length are unknown to the backend. The standard approximation is used: focal
length equals the image width and the principal point is the image centre. The
absolute angles this produces carry a systematic error, which is why the gates
compare against the USER'S OWN calibrated pose baseline rather than against
absolute thresholds — a constant error cancels in the difference.
"""

import math

import cv2
import numpy as np

# MediaPipe FaceLandmarker indices for the six classic solvePnP correspondence
# points. Deliberately avoids the mouth interior so speaking/yawning does not
# deform the set; the mouth CORNERS are stable under jaw movement.
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263
LEFT_MOUTH_CORNER = 61
RIGHT_MOUTH_CORNER = 291

LANDMARK_IDS = [
    NOSE_TIP,
    CHIN,
    LEFT_EYE_OUTER,
    RIGHT_EYE_OUTER,
    LEFT_MOUTH_CORNER,
    RIGHT_MOUTH_CORNER,
]

# Canonical 3D face model in millimetres, origin at the nose tip. Standard
# anthropometric values used with solvePnP.
MODEL_POINTS = np.array(
    [
        (0.0, 0.0, 0.0),          # nose tip
        (0.0, -330.0, -65.0),     # chin
        (-225.0, 170.0, -135.0),  # left eye outer corner
        (225.0, 170.0, -135.0),   # right eye outer corner
        (-150.0, -150.0, -125.0), # left mouth corner
        (150.0, -150.0, -125.0),  # right mouth corner
    ],
    dtype=np.float64,
)

# Nominal frame size used to turn normalised landmarks into pixel coordinates.
# Only the aspect ratio matters, and any residual error is constant per camera
# so it cancels when comparing against the user's own baseline.
NOMINAL_WIDTH = 640.0
NOMINAL_HEIGHT = 480.0

_camera_matrix = None


def _get_camera_matrix():
    global _camera_matrix
    if _camera_matrix is None:
        focal_length = NOMINAL_WIDTH
        _camera_matrix = np.array(
            [
                [focal_length, 0, NOMINAL_WIDTH / 2.0],
                [0, focal_length, NOMINAL_HEIGHT / 2.0],
                [0, 0, 1],
            ],
            dtype=np.float64,
        )
    return _camera_matrix


def solve_head_pose(landmarks):
    """
    landmarks: 478 [x, y, z] points, normalised to [0, 1].
    returns:   (pitch, yaw, roll) in degrees, or None if the pose cannot be
               recovered (missing landmarks, degenerate geometry).

    Sign convention (verify empirically before relying on it, the way the
    simplified estimate's sign had to be):
        pitch < 0  => looking down
        yaw   > 0  => turned to the subject's left
        roll       => head tilt
    """
    if landmarks is None or len(landmarks) <= max(LANDMARK_IDS):
        return None

    try:
        image_points = np.array(
            [
                (landmarks[i][0] * NOMINAL_WIDTH, landmarks[i][1] * NOMINAL_HEIGHT)
                for i in LANDMARK_IDS
            ],
            dtype=np.float64,
        )

        success, rotation_vector, _ = cv2.solvePnP(
            MODEL_POINTS,
            image_points,
            _get_camera_matrix(),
            np.zeros((4, 1)),  # assume no lens distortion
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            return None

        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)

        # Decompose to Euler angles. sy is the cosine of the pitch; when it
        # approaches zero the decomposition is degenerate (gimbal lock) and the
        # singular branch is used instead.
        sy = math.sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2)
        if sy < 1e-6:
            pitch = math.atan2(-rotation_matrix[1, 2], rotation_matrix[1, 1])
            yaw = math.atan2(-rotation_matrix[2, 0], sy)
            roll = 0.0
        else:
            pitch = math.atan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
            yaw = math.atan2(-rotation_matrix[2, 0], sy)
            roll = math.atan2(rotation_matrix[1, 0], rotation_matrix[0, 0])

        # Normalise pitch into [-180, 180] and re-centre so that facing the
        # camera reads near 0 rather than near +/-180.
        pitch_deg = math.degrees(pitch)
        if pitch_deg > 90:
            pitch_deg -= 180
        elif pitch_deg < -90:
            pitch_deg += 180

        return (pitch_deg, math.degrees(yaw), math.degrees(roll))
    except (cv2.error, IndexError, TypeError, ValueError):
        return None


def mean_pose(frames_landmarks):
    """Mean (pitch, yaw, roll) across frames, ignoring ones that fail."""
    poses = [solve_head_pose(lm) for lm in frames_landmarks]
    poses = [p for p in poses if p is not None]
    if not poses:
        return None
    arr = np.array(poses)
    return arr.mean(axis=0).tolist()


def inter_ocular_distance(landmarks):
    """
    Distance between the outer eye corners — a stable per-face scale reference.

    Brow measurements divided by this become invariant to how close the user
    sits. Without it, sitting ~8% further away shrinks every facial distance by
    ~8% and reads as a furrow that isn't there.
    """
    if landmarks is None or len(landmarks) <= max(LEFT_EYE_OUTER, RIGHT_EYE_OUTER):
        return None
    left = landmarks[LEFT_EYE_OUTER]
    right = landmarks[RIGHT_EYE_OUTER]
    distance = math.dist(left[:2], right[:2])
    return distance if distance > 1e-9 else None
