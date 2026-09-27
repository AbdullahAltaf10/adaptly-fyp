/**
 * `/study` - which document a session is about.
 *
 * `StudySession` takes a `contentId`, and until this route existed nothing ever
 * supplied one outside of tests. Everything that needs a document - the content
 * viewer, dwell tracking, simplify and summarise, the assistant's chunk
 * context, the pre-session language warnings - was therefore dormant for any
 * real learner. Reading it from the address (`/study?content=<id>`) is what
 * turns them on, and it keeps a session linkable and refresh-safe.
 *
 * No `content` in the address is still a valid session: the camera-only path
 * the page started as. It is offered rather than silently assumed, because
 * someone landing on "Study session" from the nav almost certainly meant to
 * study something.
 */

import { Link, useSearchParams } from "react-router-dom";

import StudySession from "../pages/StudySession";
import { Card } from "../ui";

export default function StudyRoute() {
  const [params, setParams] = useSearchParams();
  const contentId = params.get("content");
  const cameraOnly = params.get("mode") === "camera";

  if (!contentId && !cameraOnly) {
    return (
      <Card
        title="What would you like to study?"
        subtitle="Choose a document and Adaptly will read along with you."
      >
        <div className="flex flex-wrap gap-3 items-center">
          <Link
            to="/library"
            className="inline-flex items-center min-h-10 px-4 py-2 rounded-md border border-accent bg-accent text-on-accent font-medium hover:bg-accent-hover"
          >
            Choose a document
          </Link>
          <button
            type="button"
            className="text-accent hover:underline"
            onClick={() => setParams({ mode: "camera" })}
          >
            Start without a document
          </button>
        </div>
        <p className="mt-4 mb-0 text-sm text-muted">
          Without a document your camera is still measured, but there is nothing to simplify or
          summarise, so those kinds of support are not offered.
        </p>
      </Card>
    );
  }

  // `key` remounts the session when the document changes, so a learner who
  // switches documents does not carry the previous one's dwell, chunk and
  // capture state into the next.
  return <StudySession key={contentId ?? "camera"} contentId={contentId ?? undefined} />;
}
