import { useEffect, useState } from "react";

export default function NightModeToggle() {
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem("darkMode");
    return saved === "true";
  });

  useEffect(() => {
    if (isDark) {
      document.body.classList.add("dark-mode");
    } else {
      document.body.classList.remove("dark-mode");
    }
    localStorage.setItem("darkMode", isDark);
  }, [isDark]);

  const toggleDarkMode = () => {
    setIsDark(!isDark);
  };

  return (
    <div className="night-mode-toggle" onClick={toggleDarkMode} title={isDark ? "Light Mode" : "Dark Mode"}>
      {isDark ? "☀️" : "🌙"}
    </div>
  );
}
