"""
Module 4 endpoints - reporting what actually happened to an intervention.

Why this file has to exist at all
---------------------------------
Interventions are offered on the analyze response, so there is no endpoint for
triggering one. These endpoints exist for the other half, which is the half
that determines whether any of this is measurable.

Module 8 begins measuring recovery from a particular delivery status, and the
status differs by intervention type:

    simplify_content, bullet_summary             displayed | accepted | completed
    break_suggestion, assistant_help_prompt      accepted | completed

`offered` is in neither list, and that is correct - an intervention offered but
never rendered never reached anybody. An intervention left at `offered` is
therefore invisible to every recovery metric in the system. Firing and
forgetting would produce a full collection of events and an empty dashboard,
and nothing would fail until somebody opened it months later.

So the browser has to report back, and /intervention/{id}/status is where it
does. Every delivery path must reach a status that
`contracts.starts_recovery_measurement` accepts for its type, and the tests
assert exactly that rather than trusting this docstring.

Endpoints live with their module rather than in app/api/ - see the note in
app/api/router.py.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.intervention import contracts, service, store

router = APIRouter(prefix="/intervention", tags=["intervention"])


class StatusUpdate(BaseModel):
    session_id: str
    delivery_status: str


@router.post("/{intervention_id}/status")
def update_status(
    intervention_id: str,
    payload: StatusUpdate,
    user=Depends(get_current_user),
):
    """
    Report what happened to an intervention: displayed, accepted, dismissed,
    completed, or failed.

    Status codes, and what each one means to the client:

        200  recorded. Repeating the current status is a no-op and also 200,
             so a retry after a dropped response is safe.
        404  no such intervention for this user and session.
        409  that move is not allowed from the current status. Not a retry
             case - the client's idea of the state is wrong.
        422  not a delivery status at all.
    """
    try:
        event = service.update_status(
            user["uid"], payload.session_id, intervention_id, payload.delivery_status
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="No such intervention.")
    except contracts.InvalidTransition as error:
        raise HTTPException(status_code=409, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Could not record the delivery status.")

    return {
        "intervention_id": event["intervention_id"],
        "delivery_status": event["delivery_status"],
        # Whether this status is one Module 8 measures recovery from. Returned
        # because it is the only way a client author can tell that a delivery
        # path they built contributes nothing, without reading Module 8.
        "starts_recovery_measurement": contracts.starts_recovery_measurement(
            event["intervention_type"], event["delivery_status"]
        ),
    }


@router.get("/session/{session_id}")
def session_interventions(
    session_id: str,
    status: Optional[str] = None,
    user=Depends(get_current_user),
):
    """
    This session's interventions, oldest first.

    For reconnecting - a learner who reloads mid-session needs to know what is
    still outstanding - and for checking the lifecycle during development.
    Filtered to the caller's own events.
    """
    events = [e for e in store.list_for_session(session_id) if e.get("user_id") == user["uid"]]
    if status:
        events = [e for e in events if e.get("delivery_status") == status]
    return {
        "session_id": session_id,
        "count": len(events),
        "interventions": [
            {
                **service.client_payload(event),
                "delivery_status": event["delivery_status"],
                "timestamp": event["timestamp"],
            }
            for event in events
        ],
    }
