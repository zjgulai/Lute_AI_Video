import { useCallback, useRef, useState } from "react";

export interface SubmittingHelpers {
  submitting: boolean;
  wrap: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
  reset: () => void;
}

export function useSubmitting(): SubmittingHelpers {
  const [submitting, setSubmitting] = useState(false);
  const lockRef = useRef(false);

  const wrap = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (lockRef.current) return undefined;
    lockRef.current = true;
    setSubmitting(true);
    try {
      return await fn();
    } finally {
      lockRef.current = false;
      setSubmitting(false);
    }
  }, []);

  const reset = useCallback(() => {
    lockRef.current = false;
    setSubmitting(false);
  }, []);

  return { submitting, wrap, reset };
}
