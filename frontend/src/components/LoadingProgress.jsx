import React, { useEffect, useState } from "react";
import { LoadingText } from "./LoadingText";

const formatKilobytes = (bytes) => `${Math.round(bytes / 1024)} KB`;
// Cached sprites settle almost instantly; only show the pill when loading is
// actually noticeable so it doesn't flash on every graph rebuild.
const SPRITE_PILL_DELAY_MS = 400;

const describe = (progress) => {
  switch (progress?.stage) {
    case "waking":
      return {
        label: "Waking up the server",
        detail: `The server naps when nobody's around, so this can take up to a minute (${progress.elapsedSeconds}s)`,
      };
    case "downloading": {
      const { loaded = 0, total = 0 } = progress;
      const label = progress.label || "Loading cry data";
      if (total > 0) {
        const percent = Math.min(100, Math.round((loaded / total) * 100));
        return {
          label,
          detail: `${percent}%`,
          fraction: Math.min(1, loaded / total),
        };
      }
      return { label, detail: formatKilobytes(loaded) };
    }
    case "sprites": {
      const { loaded = 0, total = 0 } = progress;
      return {
        label: "Loading Pokémon",
        detail: `${loaded} / ${total}`,
        fraction: total > 0 ? loaded / total : 0,
      };
    }
    default:
      return { label: progress?.label || "Connecting" };
  }
};

const ProgressBar = ({ fraction, className = "" }) => (
  <div
    className={`loading-progress-bar ${className}`}
    style={{ visibility: fraction === undefined ? "hidden" : "visible" }}
  >
    <div
      className="loading-progress-fill"
      style={{ transform: `scaleX(${fraction || 0})` }}
    />
  </div>
);

export const LoadingProgress = ({ progress }) => {
  const { label, detail, fraction } = describe(progress);
  return (
    <div className="loading-progress" role="status" aria-live="polite">
      <div>
        <LoadingText label={label} />
      </div>
      <div className="loading-progress-detail">{detail || " "}</div>
      <ProgressBar fraction={fraction} />
    </div>
  );
};

// Small non-blocking indicator for sprites still loading inside the graph.
export const SpriteProgressPill = ({ progress }) => {
  const loading = Boolean(progress && progress.loaded < progress.total);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!loading) {
      setVisible(false);
      return undefined;
    }
    const timer = setTimeout(() => setVisible(true), SPRITE_PILL_DELAY_MS);
    return () => clearTimeout(timer);
  }, [loading]);

  if (!loading || !visible) return null;

  return (
    <div className="sprite-progress-pill" role="status" aria-live="polite">
      <span>
        Loading Pokémon {progress.loaded} / {progress.total}
      </span>
      <ProgressBar
        fraction={progress.loaded / progress.total}
        className="loading-progress-bar-small"
      />
    </div>
  );
};
