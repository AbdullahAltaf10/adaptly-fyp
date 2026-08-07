import math

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


def eye_aspect_ratio(landmarks, eye_indices):
    points = [landmarks[i] for i in eye_indices]
    p1, p2, p3, p4, p5, p6 = points
    vertical1 = math.dist(p2[:2], p6[:2])
    vertical2 = math.dist(p3[:2], p5[:2])
    horizontal = math.dist(p1[:2], p4[:2])
    if horizontal == 0:
        return 0
    return (vertical1 + vertical2) / (2.0 * horizontal)


def estimate_head_pose(landmarks):
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


def eyebrow_eye_distance(landmarks, eyebrow_indices, eye_upper_indices):
    def avg_point(indices):
        xs = [landmarks[i][0] for i in indices]
        ys = [landmarks[i][1] for i in indices]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    eyebrow_center = avg_point(eyebrow_indices)
    eye_center = avg_point(eye_upper_indices)
    return math.dist(eyebrow_center, eye_center)


def extract_9_features(landmarks):
    """
    landmarks: list of 478 [x, y, z] points from MediaPipe FaceLandmarker
    returns: list of 9 floats, or None if landmarks is None
    """
    if landmarks is None:
        return None

    left_ear = eye_aspect_ratio(landmarks, LEFT_EYE)
    right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE)
    blink_rate = (left_ear + right_ear) / 2
    eye_openness = blink_rate

    pitch, yaw, roll = estimate_head_pose(landmarks)
    gaze_x, gaze_y = gaze_direction(landmarks)

    left_brow_eye = eyebrow_eye_distance(landmarks, LEFT_EYEBROW, LEFT_EYE_UPPER)
    right_brow_eye = eyebrow_eye_distance(landmarks, RIGHT_EYEBROW, RIGHT_EYE_UPPER)
    brow_raise = (left_brow_eye + right_brow_eye) / 2

    inter_brow_distance = math.dist(
        landmarks[LEFT_EYEBROW_INNER][:2], landmarks[RIGHT_EYEBROW_INNER][:2]
    )

    return [gaze_x, gaze_y, blink_rate, pitch, yaw, roll, eye_openness, brow_raise, inter_brow_distance]