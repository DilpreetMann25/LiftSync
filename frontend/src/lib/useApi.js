/**
 * A hook for loading data from the API.
 *
 * Every data screen needs the same three things: the data, whether it
 * is still loading, and what went wrong. Writing that by hand in each
 * component means three useStates and a useEffect repeated a dozen
 * times, and one of them will forget the error case.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export function useApi(fetcher, deps = [], { skip = false } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(!skip);
  const [error, setError] = useState(null);

  // Bumping this forces a re-run, which is how refresh() works.
  const [nonce, setNonce] = useState(0);
  const latestRequest = useRef(0);

  useEffect(() => {
    if (skip) {
      setLoading(false);
      return;
    }

    // Guards against a race: switch exercises quickly and two requests
    // are in flight at once. If the first resolves last, it would
    // overwrite the newer data with stale results. Only the most
    // recent request is allowed to set state.
    const requestId = ++latestRequest.current;

    setLoading(true);
    setError(null);

    fetcher()
      .then((result) => {
        if (requestId === latestRequest.current) setData(result);
      })
      .catch((err) => {
        if (requestId === latestRequest.current) setError(err);
      })
      .finally(() => {
        if (requestId === latestRequest.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, skip]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return { data, loading, error, refresh, setData };
}
