import { useEffect, useState } from "react";

/** Re-renders every `interval` ms while `active`, returning Date.now(). */
export function useNow(active: boolean, interval = 250): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), interval);
    return () => clearInterval(t);
  }, [active, interval]);
  return active ? now : Date.now();
}
