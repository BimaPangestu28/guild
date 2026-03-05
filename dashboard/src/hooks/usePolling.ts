import { useState, useEffect, useCallback } from 'react';

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 5000, fallback: T) {
  const [data, setData] = useState<T>(fallback);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(false);
    } catch {
      setError(true);
    }
  }, [fetcher]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { data, error, refresh };
}
