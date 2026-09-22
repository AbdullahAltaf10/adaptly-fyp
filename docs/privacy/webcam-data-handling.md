# Privacy — how webcam data is handled

The project's central privacy claim is that **no video is ever recorded, stored
or transmitted**. This document states precisely what that means, what *is*
handled, and where the claim has limits.

## What happens to a camera frame

```
webcam frame
   |
   v  in the browser, on the learner's own machine
MediaPipe FaceLandmarker
   |
   +--> 478 landmark points (x, y, z numbers)  --> sent to the server
   |
   +--> the image itself                       --> DISCARDED immediately
```

The picture never leaves the browser. It is not written to disk, not held in a
buffer, and not sent anywhere. What crosses the network is a list of numbers.

**This is not a policy that could be violated by a configuration mistake — the
server has no endpoint that accepts an image.** `/engagement/analyze` takes
landmark coordinates and nothing else.

## What the server receives

| Data | Stored? | Notes |
|---|---|---|
| 478 landmark points per frame | **No** | Held in memory for the request, converted to 9 features, discarded |
| The 9 derived features | **No** | Used for the prediction, then discarded |
| Calibration baseline | **Yes** | 9 numbers plus a head-pose baseline, per user |
| Engagement state + confidence | Returned | Persisted only when Module 8 exists |

Landmarks are never written to the database and never written to a log.

## Are facial landmarks personal data?

**Yes — treat them as such.** 478 points describing the geometry of someone's
face are biometric-adjacent: they describe a specific person's features, and
research has shown facial geometry can be identifying.

That is why they are processed in memory and discarded rather than stored, even
though storing them would make debugging and later evaluation easier. The
convenience is not worth creating a database of people's facial geometry.

## What *is* stored, and why

**Calibration baseline** — nine averaged feature values plus a head-pose
baseline, per user.

Necessary because laptop webcams sit above the screen: a user looking normally
at their screen reads as an extreme downward head angle by the training data's
standards, measured at about 2.48 standard deviations off. Without correcting
for it, attentive users are consistently classified as distracted.

This is an average of averages, not a face. It cannot be used to reconstruct
anyone's appearance. It is per-user and removed with the user's record.

## Logging

**Nothing in Module 3 logs landmarks, features or calibration values.**

The diagnostics returned by `/engagement/analyze` — confirmation streaks,
fatigue ratios, stillness variances — are development instruments returned in
the response and not written anywhere.

Anyone adding logging here should not log:

- landmark arrays or any subset of them
- raw or calibrated feature values
- calibration offsets or baselines

State labels and confidences are fine.

## What the learner is told

The session cannot start until the learner has read a screen stating that the
camera measures engagement, that no video is recorded or transmitted, and that
only numeric measurements leave the browser. The camera is not requested before
that screen is dismissed.

## Limits of the claim, stated honestly

**"Processing is local" applies to the image, not the analysis.** The picture is
processed and discarded locally, but the *derived numbers* are sent to a server
and analysed there. It would be inaccurate to describe the whole pipeline as
on-device.

**Landmarks are in transit.** They cross the network to reach the server. HTTPS
protects them in transit in a deployed environment; the current development
setup uses plain HTTP on localhost, which is fine locally and **must not be
carried into deployment**.

**A calibration record identifies a user.** It is keyed by user id and describes
their facial baseline. It is not a face, but it is not anonymous either.

**Multiple people under one login share one baseline.** The calibration is
stored per account. If several people test using the same login, each must
recalibrate, and their sessions cannot be told apart afterwards.

## Deployment checklist

Before this runs anywhere other than a developer's machine:

- [ ] HTTPS enforced — landmarks must not travel in plain text
- [ ] CORS tightened from the current any-localhost-port rule to the real origin
- [ ] Confirm no logging of landmarks, features or calibration has crept in
- [ ] Calibration records removed when a user deletes their account
- [ ] Retention decided for engagement events once Module 8 stores them
