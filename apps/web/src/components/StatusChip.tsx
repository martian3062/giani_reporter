import type { EpisodeStatus, PostStatus, RenderStatus } from "../types";

type Status =
  | EpisodeStatus
  | PostStatus
  | RenderStatus
  | "live"
  | "demo"
  | "connecting";

const labels: Record<Status, string> = {
  planning: "Planning",
  draft: "Draft",
  approved: "Approved",
  packaged: "Packaged",
  queued: "Queued",
  running: "In progress",
  complete: "Complete",
  failed: "Failed",
  generating: "Generating",
  review: "In review",
  publishing: "Publishing",
  published: "Published",
  live: "Live API",
  demo: "Demo data",
  connecting: "Connecting",
};

export function StatusChip({ status }: { status: Status }) {
  return (
    <span className={`status-chip status-${status}`}>
      <span className="status-dot" aria-hidden="true" />
      {labels[status]}
    </span>
  );
}
