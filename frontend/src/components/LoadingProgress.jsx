import React from "react";
import { LoadingText } from "./LoadingText";

const formatKilobytes = (bytes) => `${Math.round(bytes / 1024)} KB`;

const describe = (progress) => {
  switch (progress?.stage) {
    case "waking":
      return {
        label: "Waking up the server",
        detail: `The server naps when nobody's around, so this can take up to a minute (${progress.elapsedSeconds}s)`,
      };
    case "downloading": {
      const { loaded = 0, total = 0 } = progress;
      if (total > 0) {
        const percent = Math.min(100, Math.round((loaded / total) * 100));
        return {
          label: "Loading cry data",
          detail: `${percent}%`,
          fraction: Math.min(1, loaded / total),
        };
      }
      return { label: "Loading cry data", detail: formatKilobytes(loaded) };
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
      return { label: "Connecting" };
  }
};

export const LoadingProgress = ({ progress }) => {
  const { label, detail, fraction } = describe(progress);
  return (
    <div className="loading-progress" role="status" aria-live="polite">
      <div>
        <LoadingText label={label} />
      </div>
      <div className="loading-progress-detail">{detail || " "}</div>
      <div
        className="loading-progress-bar"
        style={{ visibility: fraction === undefined ? "hidden" : "visible" }}
      >
        <div
          className="loading-progress-fill"
          style={{ transform: `scaleX(${fraction || 0})` }}
        />
      </div>
    </div>
  );
};
