"use client";

import { useState } from "react";

const TTYD_URL = process.env.NEXT_PUBLIC_TTYD_URL || "http://localhost:7681";

export default function BoardPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <h1 className="text-lg font-semibold">Board</h1>
        <a
          href={TTYD_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Open full screen ↗
        </a>
      </div>

      {isLoading && !hasError && (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-muted-foreground">Loading board terminal...</p>
        </div>
      )}

      {hasError && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <p className="text-muted-foreground">
            Unable to connect to board terminal at {TTYD_URL}
          </p>
          <button
            onClick={() => {
              setHasError(false);
              setIsLoading(true);
            }}
            className="px-4 py-2 text-sm rounded-md border hover:bg-accent"
          >
            Retry
          </button>
        </div>
      )}

      <iframe
        src={TTYD_URL}
        className={`flex-1 w-full border-0 ${isLoading || hasError ? "hidden" : ""}`}
        title="QuinnAI Board"
        sandbox="allow-scripts allow-same-origin"
        onLoad={() => setIsLoading(false)}
        onError={() => {
          setIsLoading(false);
          setHasError(true);
        }}
      />
    </div>
  );
}
