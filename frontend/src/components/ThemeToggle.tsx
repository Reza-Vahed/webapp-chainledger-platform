import { useEffect, useState } from "react";

type Theme = "light" | "dark";

function getInitialTheme(): Theme {
  const stored = window.localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme((current) => (current === "light" ? "dark" : "light"))}
      aria-label={theme === "light" ? "Dark Mode aktivieren" : "Light Mode aktivieren"}
      title={theme === "light" ? "Dark Mode aktivieren" : "Light Mode aktivieren"}
    >
      {theme === "light" ? "🌙" : "☀️"}
    </button>
  );
}
