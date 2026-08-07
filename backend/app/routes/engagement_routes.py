from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.core.dependencies import get_current_user
from app.core.db import db
from app.ml.engagement_model import predict_engagement
from app.ml.feature_extraction import extract_9_features
from app.ml.calibration import compute_user_baseline, compute_offset, apply_calibration
from app.ml import smoothing, fatigue, recovery, deep_thinking, furrow, head_pose

router = APIRouter(prefix="/engagement", tags=["engagement"])


class FrameData(BaseModel):
    landmarks: Optional[List[List[float]]] = None


class CalibrateRequest(BaseModel):
    frames: List[FrameData]


class EngagementAnalyzeRequest(BaseModel):
    frames: List[FrameData]
    # Optional: when present, predictions are smoothed across consecutive
    # windows for this session. When absent the raw prediction is returned,
    # exactly as before smoothing existed.
    session_id: Optional[str] = None


def extract_feature_sequence(frames: List[FrameData]) -> list:
    feature_sequence = []
    last_valid = None
    for frame in frames:
        feats = extract_9_features(frame.landmarks)
        if feats is not None:
            last_valid = feats
            feature_sequence.append(feats)
        elif last_valid is not None:
            feature_sequence.append(last_valid)
        else:
            feature_sequence.append(None)
    return feature_sequence


@router.post("/calibrate")
def calibrate(payload: CalibrateRequest, user=Depends(get_current_user)):
    feature_sequence = extract_feature_sequence(payload.frames)
    baseline = compute_user_baseline(feature_sequence)

    if baseline is None:
        raise HTTPException(status_code=422, detail="No face detected during calibration")

    offset = compute_offset(baseline)

    # Captured alongside the feature offset because the rule-based gates work in
    # solvePnP degrees and normalised brow units, neither of which the feature
    # offset covers. Both are per-user and per-camera, exactly like the offset.
    raw_landmarks = [frame.landmarks for frame in payload.frames]
    pose_baseline = head_pose.mean_pose(raw_landmarks)
    brow_baseline = furrow.mean_normalised_brow(raw_landmarks)

    db.calibration.update_one(
        {"uid": user["uid"]},
        {"$set": {
            "offset": offset,
            "pose_baseline": pose_baseline,
            "brow_baseline": brow_baseline,
        }},
        upsert=True,
    )

    return {
        "message": "Calibration complete",
        "offset": offset,
        "pose_baseline": pose_baseline,
        "brow_baseline": brow_baseline,
    }


@router.post("/analyze")
def analyze_engagement(payload: EngagementAnalyzeRequest, user=Depends(get_current_user)):
    if len(payload.frames) != 10:
        raise HTTPException(status_code=400, detail="Exactly 10 frames are required")

    feature_sequence = extract_feature_sequence(payload.frames)

    # replace any remaining None frames (no face detected at all yet) with zeros
    feature_sequence = [f if f is not None else [0.0] * 9 for f in feature_sequence]

    calibration_doc = db.calibration.find_one({"uid": user["uid"]})
    if calibration_doc:
        feature_sequence = apply_calibration(feature_sequence, calibration_doc["offset"])

    result = predict_engagement(feature_sequence)

    if not payload.session_id:
        return result  # unchanged legacy response when no session_id is sent

    response = smoothing.update(
        user["uid"], payload.session_id, result["state"], result["confidence"]
    )
    # solvePnP pose relative to the user's own baseline. None when the user has
    # not recalibrated since solvePnP was added, or when the pose cannot be
    # recovered — the gates fall back to the simplified estimate in that case.
    raw_landmarks = [frame.landmarks for frame in payload.frames]
    pose_baseline = calibration_doc.get("pose_baseline") if calibration_doc else None
    brow_baseline = calibration_doc.get("brow_baseline") if calibration_doc else None
    current_pose = head_pose.mean_pose(raw_landmarks)
    pose_pitch_delta = (
        current_pose[0] - pose_baseline[0]
        if current_pose is not None and pose_baseline
        else None
    )

    response.update(
        fatigue.update(
            user["uid"],
            payload.session_id,
            feature_sequence,
            calibrated=calibration_doc is not None,
            pose_pitch_delta=pose_pitch_delta,
        )
    )
    # Measurement only — deliberately does NOT influence `state`. Struggling is
    # a model class, so the override stays off until the threshold is tuned
    # against real readings (see furrow.py docstring).
    response.update(
        furrow.update(
            user["uid"],
            payload.session_id,
            raw_landmarks,
            brow_baseline,
            pose_pitch_delta,
            calibrated=calibration_doc is not None,
        )
    )

    dt = deep_thinking.update(
        user["uid"],
        payload.session_id,
        feature_sequence,
        response["state"],
        calibrated=calibration_doc is not None,
        pose_pitch_delta=pose_pitch_delta,
    )
    response.update(dt)

    # Recovery sees the EFFECTIVE state, so windows judged to be reflection are
    # not counted as a dip the learner later "recovers" from — they never
    # disengaged in the first place.
    effective_state = "Deep Thinking" if dt["deep_thinking"] else response["state"]

    # fed the smoothed state, so noisy single-window flips can't fake a recovery
    response.update(recovery.update(user["uid"], payload.session_id, effective_state))
    return response