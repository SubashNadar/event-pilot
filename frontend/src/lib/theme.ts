import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "eventpilot.theme";

const initialTheme = (): Theme => {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* storage unavailable */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
};

/** Light or dark, remembered per browser. `.dark` on <html> drives both the Tailwind tokens and the app theme. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.dataset.theme = theme;
    try { localStorage.setItem(KEY, theme); } catch { /* storage unavailable */ }
  }, [theme]);
  return [theme, () => setTheme((current) => (current === "dark" ? "light" : "dark"))];
}
