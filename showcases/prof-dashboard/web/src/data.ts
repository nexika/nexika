import { useEffect, useState } from "react";
import { api } from "./lib";

/** Fetch one API path; refetches when the path changes. */
export function useApi<T>(path: string): { data?: T; error?: Error } {
  const [state, setState] = useState<{ path: string; data?: T; error?: Error }>({ path });
  useEffect(() => {
    let live = true;
    api<T>(path).then(
      (data) => live && setState({ path, data }),
      (error: Error) => live && setState({ path, error }),
    );
    return () => { live = false; };
  }, [path]);
  return state.path === path ? state : {};
}
