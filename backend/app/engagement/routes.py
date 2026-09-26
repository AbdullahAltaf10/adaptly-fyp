"""
Module 3 endpoints — calibration, analysis, and session lifecycle.

Privacy: this module never receives an image. The browser runs MediaPipe
locally, converts each frame to 478 numeric landmark points, and discards the
picture. Only those numbers arrive here. Nothing in this file writes landmarks
or calibration values to a log. See docs/privacy/webcam-data-handling.md.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.core.db import db
from app.engagement import (
    contracts,
    deep_thinking,
    fatigue,
    furrow,
    recovery,
    rereading,
    session as session_state,
    smoothing,
)
from app.engagement.analytics_sink import record_engagement_event
from app.engagement.calibration import apply_calibration, compute_offset, compute_user_baseline
from app.intervention import service as intervention
from backend.app.analytics.service import session_lifecycle
from ml.inference import head_pose
from ml.inference.features import InvalidLandmarksError, extract_features
from ml.inference.model import predict

router = APIRouter(prefix="/engagement", tags=["engagement"])

WINDOW_SIZE = 10
FEATURE_COUNT = 9


class FrameData(BaseModel):
    landmarks: Optional[List[List[float]]] = None


class CalibrateRequest(BaseModel):
    frames: List[FrameData]


class AnalyzeRequest(BaseModel):
    frames: List[FrameData]
    session_id: Optional[str] = None
    content_id: Optional[str] = None
    chunk_id: Optional[str] = None

    # How long the learner has been on this chunk. Module 4 uses it to decide
    # how intrusive a response is justified - rewriting a paragraph somebody
    # glanced at for three seconds is not support, it is interference.
    #
    # The browser measures it because the server cannot: scrolling produces no
    # request. Until the content viewer exists (issue #12) nothing sends it, it
    # stays 0, and the dwell-gated responses simply never fire. That is the
    # right failure - no dwell evidence, no dwell-based intervention.
    dwell_seconds: Optional[float] = 0.0


class SessionRequest(BaseModel):
    session_id: str
    # Optional and additive: only used by /session/start, to create Module
    # 8's own session record (Issue #82). /session/end ignores it. Existing
    # callers that never send it keep working exactly as before.
    content_id: Optional[str] = None


def extract_feature_sequence(frames: List[FrameData]) -> list:
    """
    Turn frames into feature rows, carrying the last good row forward when a
    frame has no face.

    Invalid landmark data is treated as a missing frame rather than raising:
    one bad frame in ten should not fail the whole window, and the >=7 valid
    frame rule on the client already guards against a window that is mostly
    noise.
    """
    sequence = []
    last_valid = None
    for frame in frames:
        try:
            features = extract_features(frame.landmarks)
        except InvalidLandmarksError:
            features = None

        if features is not None:
            last_valid = features
            sequence.append(features)
        elif last_valid is not None:
            sequence.append(last_valid)
        else:
            sequence.append(None)
    return sequence


@router.post("/session/start")
def start_session(payload: SessionRequest, user=Depends(get_current_user)):
    """Begin a session, clearing any rule state left over from a previous one."""
    result = session_state.start(user["uid"], payload.session_id)
    session_lifecycle.create_session_safely(user["uid"], payload.session_id, payload.content_id)
    return result


@router.post("/session/end")
def end_session(payload: SessionRequest, user=Depends(get_current_user)):
    """Finish a session and release its rule state immediately."""
    # Module 4's cooldown is per-session and in memory, like the rules above,
    # and a new session must not inherit the previous one's quiet period. Kept
    # here rather than inside session.py so the engagement rules stay a closed
    # set that knows nothing about interventions.
    intervention.on_session_end(user["uid"], payload.session_id)
    result = session_state.end(user["uid"], payload.session_id)
    # Module 8's own finalization (Issue #82). Failure-safe: never raises,
    # so a database or analytics problem cannot prevent a session from
    # ending for the learner.
    session_lifecycle.finalize_session_safely(user["uid"], payload.session_id)
    return result


@router.post("/calibrate")
def calibrate(payload: CalibrateRequest, user=Depends(get_current_user)):
    """
    Record this user's own baseline.

    Necessary because laptop webcams sit above the screen: a user looking
    normally at their screen reads as an extreme downward head angle by the
    training data's standards - measured about 2.48 standard deviations off.
    Without this, attentive users are classified as distracted.
    """
    sequence = extract_feature_sequence(payload.frames)
    baseline = compute_user_baseline(sequence)
    if baseline is None:
        raise HTTPException(status_code=422, detail="No face was detected during calibration.")

    raw_landmarks = [frame.landmarks for frame in payload.frames]

    db.calibration.update_one(
        {"uid": user["uid"]},
        {"$set": {
            "offset": compute_offset(baseline),
            "pose_baseline": head_pose.mean_pose(raw_landmarks),
            "brow_baseline": furrow.mean_normalised_brow(raw_landmarks),
        }},
        upsert=True,
    )
    return {"message": "Calibration complete"}


@router.post("/analyze")
def analyze(payload: AnalyzeRequest, user=Depends(get_current_user)):
    """
    Classify one 10-second window.

    Returns the engagement event in contract shape, plus a separate
    `diagnostics` object. The diagnostics are development instruments and are
    deliberately outside the event: the contract sets additionalProperties to
    false, and these values are not part of the exchange format.
    """
    if len(payload.frames) != WINDOW_SIZE:
        raise HTTPException(
            status_code=400, detail=f"Exactly {WINDOW_SIZE} frames are required."
        )

    uid = user["uid"]
    session_id = payload.session_id

    def work():
        sequence = extract_feature_sequence(payload.frames)
        # Frames before the first detected face have no value to carry forward.
        sequence = [f if f is not None else [0.0] * FEATURE_COUNT for f in sequence]

        calibration_doc = db.calibration.find_one({"uid": uid})
        calibrated = calibration_doc is not None
        if calibrated:
            sequence = apply_calibration(sequence, calibration_doc["offset"])

        prediction = predict(sequence)

        raw_landmarks = [frame.landmarks for frame in payload.frames]
        pose_baseline = calibration_doc.get("pose_baseline") if calibration_doc else None
        brow_baseline = calibration_doc.get("brow_baseline") if calibration_doc else None
        current_pose = head_pose.mean_pose(raw_landmarks)
        pose_pitch_delta = (
            current_pose[0] - pose_baseline[0]
            if current_pose is not None and pose_baseline else None
        )

        # Without a session id there is nowhere to keep history, so the rule
        # layers cannot run. Return the raw model output on its own.
        if not session_id:
            return {
                "event": None,
                "state": prediction["state"],
                "confidence": prediction["confidence"],
                # Same shape as the full response so a client never has to
                # check whether the key is there. Interventions need a session
                # anyway - there is nowhere to keep a cooldown without one.
                "intervention": None,
                "diagnostics": {"note": "session_id is required for smoothing and rules"},
            }

        session_state.touch(uid, session_id)

        smoothed = smoothing.update(uid, session_id, prediction["state"], prediction["confidence"])
        fatigue_result = fatigue.update(
            uid, session_id, sequence, calibrated=calibrated,
            pose_pitch_delta=pose_pitch_delta,
        )
        furrow_result = furrow.update(
            uid, session_id, raw_landmarks, brow_baseline, pose_pitch_delta,
            calibrated=calibrated,
        )
        dt_result = deep_thinking.update(
            uid, session_id, sequence, smoothed["state"], calibrated=calibrated,
            pose_pitch_delta=pose_pitch_delta,
        )

        # Reflection is applied before recovery, so a long stretch of genuine
        # thinking is not later counted as a dip the learner "recovered" from.
        effective_state = "deep_thinking" if dt_result["deep_thinking"] else smoothed["state"]
        recovery_result = recovery.update(uid, session_id, effective_state)

        # Precedence, which layer produced the reported state, and - this part
        # was wrong until now - a confidence that describes THAT state.
        #
        # The event always carried prediction["confidence"], the model's
        # confidence in its own raw winning class. That is the right number in
        # only some of the cases below:
        #
        #   fatigued    state comes from a rule, so the model's confidence
        #               describes a different class entirely
        #   recovered   same
        #   smoothing   the displayed state is deliberately held through a
        #               transition, so it can differ from the raw class the
        #               confidence belongs to
        #
        # Module 8 persists this field, so a wrong value does not merely
        # mislead a reader - it accumulates.
        if fatigue_result["fatigued"]:
            state, source = "fatigued", contracts.SOURCE_RULE
            # How much of the recent history breached the low-openness
            # threshold. 0.80 is the firing point; higher means more of the
            # window agreed. Already computed, already 0-1, and it is evidence
            # about fatigue rather than about a model class.
            confidence = fatigue_result["fatigue_ratio"]
        elif recovery_result["recovered"]:
            state, source = "recovered", contracts.SOURCE_RULE
            # Deterministic: fires when a sustained bad run is followed by a
            # confirmed return to focused, and it consumes the SMOOTHED state,
            # so the trigger is already confirmed rather than one noisy frame.
            # There is no graded evidence to report. RULE_CERTAIN says the
            # rule's condition was met - not that the learner has certainly
            # recovered. See docs/model/model-card.md for what the rule can
            # and cannot support.
            confidence = contracts.RULE_CERTAIN
        elif dt_result["deep_thinking"]:
            state, source = smoothed["state"], contracts.SOURCE_HYBRID
            confidence = contracts.confidence_for(prediction, state)
        else:
            state, source = smoothed["state"], contracts.SOURCE_MODEL
            confidence = contracts.confidence_for(prediction, state)

        event = contracts.build_engagement_event(
            user_id=uid,
            session_id=session_id,
            state=state,
            confidence=confidence,
            source=source,
            features=contracts.mean_features(sequence),
            content_id=payload.content_id,
            chunk_id=payload.chunk_id,
            deep_thinking_detected=dt_result["deep_thinking"],
            gaze_regression_detected=False,   # never measured; see rereading.py
        )

        record_engagement_event(event)

        # Module 4. Wrapped because engagement detection works today and this
        # is new: a fault in the intervention path must not take the analyze
        # endpoint down with it. The reason is reported rather than swallowed.
        try:
            decision = intervention.evaluate(
                uid,
                session_id,
                state=state,
                source=source,
                confidence=prediction["confidence"],
                # The two signals the tiers were measured on, kept separate -
                # see ml/evaluation/trigger_fusion.py. Deliberately the raw
                # per-window class rather than the smoothed state: smoothing
                # needs three consecutive agreeing windows before it displays
                # struggling, which a learner whose recall is 0.28 almost never
                # produces. Smoothing exists for display stability; the
                # intervention's stability comes from its cooldown instead.
                raw_struggling=prediction["state"] == "struggling",
                brow_struggling=bool(furrow_result["furrowed"]),
                content_id=payload.content_id,
                chunk_id=payload.chunk_id,
                dwell_seconds=payload.dwell_seconds,
                engagement_event_id=event["event_id"],
            )
        except Exception as error:
            decision = {"intervention": None, "note": f"intervention path failed: {error}"}

        return {
            "event": event,
            "state": state,
            "confidence": prediction["confidence"],
            # None most of the time. When present the client renders it and
            # then reports delivery to /intervention/{id}/status - an
            # intervention left at `offered` is measured by nothing.
            "intervention": decision["intervention"],
            # Development instruments only. Not part of the contract, and not
            # shown to a learner in the finished product - scope section 6.8
            # requires no scores or indicators during an active session.
            "diagnostics": {
                "raw_state": prediction["state"],
                "smoothing": smoothed,
                "fatigue": fatigue_result,
                "furrow": furrow_result,
                "deep_thinking": dt_result,
                "recovery": recovery_result,
                "rereading": rereading.detect_rereading([]),
                "intervention": decision["note"],
            },
        }

    # Serialised per session so overlapping windows cannot corrupt rule state.
    return session_state.process_exclusively(uid, session_id or "no-session", work)
