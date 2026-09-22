"""
Feature extraction: 478 MediaPipe landmarks -> the 9 values the model expects.

Pure functions, no web framework, so this can be exercised from a notebook or a
test without starting a server.

FEATURE ORDER IS LOAD-BEARING. It must match the order used at training time,
in ml/artifacts/MANIFEST.json, and in the calibration reference file. Reordering
these silently produces confident nonsense rather than an error.
"""

import math

# --- MediaPipe FaceLandmarker indices ---
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
LEFT_IRIS = [468, 469, 470, 471]
RIGHT_IRIS = [473, 474, 475, 476]
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_CORNER = 33
RIGHT_EYE_CORNER = 263
LEFT_EYEBROW = [70, 63, 105, 66, 107]
RIGHT_EYEBROW = [336, 296, 334, 293, 300]
LEFT_EYEBROW_INNER = 55
RIGHT_EYEBROW_INNER = 285
LEFT_EYE_UPPER = [160, 158]
RIGHT_EYE_UPPER = [385, 387]

FEATURE_NAMES = [
    "gaze_x", "gaze_y", "blink_rate", "pitch", "yaw",
    "roll", "eye_openness", "brow_raise", "inter_brow",
]

EXPECTED_LANDMARK_COUNT = 478
FEATURE_COUNT = 9
WINDOW_SIZE = 10


class InvalidLandmarksError(ValueError):
    """Raised when landmark input cannot be trusted."""


def validate_landmarks(landmarks) -> None:
    """
    Reject landmark data that cannot be trusted, rather than extracting
    plausible-looking features from it.

    The prototype indexed straight into whatever arrived. A short array raised
    IndexError deep inside extraction; coordinates outside [0, 1] (which
    MediaPipe produces when a face is partly out of frame, and which a
    hand-crafted request could contain anything) silently skewed every feature.
    """
    if landmarks is None:
        raise InvalidLandmarksError("landmarks are missing")

    if not isinstance(landmarks, (list, tuple)):
        raise InvalidLandmarksError("landmarks must be a list of points")

    if len(landmarks) != EXPECTED_LANDMARK_COUNT:
        raise InvalidLandmarksError(
            f"expected {EXPECTED_LANDMARK_COUNT} landmarks, got {len(landmarks)}"
        )

    for index in (NOSE_TIP, CHIN, LEFT_EYE_CORNER, RIGHT_EYE_CORNER,
                  LEFT_EYEBROW_INNER, RIGHT_EYEBROW_INNER):
        point = landmarks[index]
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise InvalidLandmarksError(f"landmark {index} is not an (x, y, z) point")

        x, y = point[0], point[1]
        if not all(isinstance(v, (int, float)) for v in (x, y)):
            raise InvalidLandmarksError(f"landmark {index} has non-numeric coordinates")

        # MediaPipe normalises to [0, 1] against the frame. A small margin is
        # allowed because points just outside the frame are legitimate.
        if not (-0.5 <= x <= 1.5 and -0.5 <= y <= 1.5):
            raise InvalidLandmarksError(
                f"landmark {index} is far outside the frame ({x:.2f}, {y:.2f})"
            )


def eye_aspect_ratio(landmarks, eye_indices) -> float:
    p1, p2, p3, p4, p5, p6 = (landmarks[i] for i in eye_indices)
    vertical1 = math.dist(p2[:2], p6[:2])
    vertical2 = math.dist(p3[:2], p5[:2])
    horizontal = math.dist(p1[:2], p4[:2])
    if horizontal == 0:
        return 0.0
    return (vertical1 + vertical2) / (2.0 * horizontal)


def estimate_head_pose(landmarks):
    """
    Simplified geometric head pose.

    NOT solvePnP. The scope document specifies solvePnP, and it IS implemented
    (head_pose.py) — but the trained model and scaler were fitted on these
    simplified values, which live on a completely different numeric scale.
    Feeding real degrees to the model would supply out-of-distribution input.
    See docs/model/model-card.md.

    Measured sign convention: tilting the head down makes `pitch` INCREASE.
    """
    nose = landmarks[NOSE_TIP]
    chin = landmarks[CHIN]
    left_eye = landmarks[LEFT_EYE_CORNER]
    right_eye = landmarks[RIGHT_EYE_CORNER]
    yaw = (nose[0] - (left_eye[0] + right_eye[0]) / 2) * 100
    pitch = (nose[1] - chin[1]) * 100
    roll = math.degrees(math.atan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0]))
    return pitch, yaw, roll


def gaze_direction(landmarks):
    def avg_point(indices):
        xs = [landmarks[i][0] for i in indices]
        ys = [landmarks[i][1] for i in indices]
        return sum(xs) / len(xs), sum(ys) / len(ys)

    left_iris = avg_point(LEFT_IRIS)
    right_iris = avg_point(RIGHT_IRIS)
    left_eye = avg_point(LEFT_EYE)
    right_eye = avg_point(RIGHT_EYE)

    gaze_x = ((left_iris[0] - left_eye[0]) + (right_iris[0] - right_eye[0])) / 2
    gaze_y = ((left_iris[1] - left_eye[1]) + (right_iris[1] - right_eye[1])) / 2
    return gaze_x, gaze_y


def eyebrow_eye_distance(landmarks, eyebrow_indices, eye_upper_indices) -> float:
    def avg_point(indices):
        xs = [landmarks[i][0] for i in indices]
        ys = [landmarks[i][1] for i in indices]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    return math.dist(avg_point(eyebrow_indices), avg_point(eye_upper_indices))


def extract_features(landmarks, *, validate: bool = True):
    """
    Return the 9 features in FEATURE_NAMES order, or None if landmarks are absent.

    KNOWN LIMITATION — blink_rate is not a blink rate. It is the same eye-aspect
    ratio value as eye_openness, because a blink lasts 100-400 ms and frames are
    sampled once per second, so a genuine blink rate cannot be measured from
    this input at all. Correcting it requires both a higher sampling rate and a
    retrain, since the model was fitted on the duplicated value. Documented in
    docs/model/model-card.md rather than silently carried.
    """
    if landmarks is None:
        return None

    if validate:
        validate_landmarks(landmarks)

    left_ear = eye_aspect_ratio(landmarks, LEFT_EYE)
    right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE)
    ear = (left_ear + right_ear) / 2

    blink_rate = ear        # see the limitation above
    eye_openness = ear

    pitch, yaw, roll = estimate_head_pose(landmarks)
    gaze_x, gaze_y = gaze_direction(landmarks)

    brow_raise = (
        eyebrow_eye_distance(landmarks, LEFT_EYEBROW, LEFT_EYE_UPPER)
        + eyebrow_eye_distance(landmarks, RIGHT_EYEBROW, RIGHT_EYE_UPPER)
    ) / 2

    inter_brow = math.dist(
        landmarks[LEFT_EYEBROW_INNER][:2], landmarks[RIGHT_EYEBROW_INNER][:2]
    )

    return [gaze_x, gaze_y, blink_rate, pitch, yaw, roll,
            eye_openness, brow_raise, inter_brow]
