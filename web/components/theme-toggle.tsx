"use client";

import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);
  useEffect(() => {
    const saved = window.localStorage.getItem("dm-theme");
    const initial = saved === "light" || saved === "dark" ? saved : (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    setTheme(initial);
    document.documentElement.dataset.theme = initial;
  }, []);
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("dm-theme", next);
  }
  return <button className="theme-toggle" type="button" onClick={toggle} aria-label="Toggle colour theme">{theme === "dark" ? "☼" : "◐"}</button>;
}
