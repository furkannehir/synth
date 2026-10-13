import { createContext, useContext, useEffect, useState } from 'react';
import { THEMES, THEME_CLASSES, resolveTheme } from '../utils/themes';

const ThemeContext = createContext();

export const ThemeProvider = ({ children }) => {
  const [storedTheme, updateTheme] = useState(() => {
    try { return resolveTheme(localStorage.getItem('synth-theme')); }
    catch { return resolveTheme(null); }
  });
  const theme = resolveTheme(storedTheme);

  useEffect(() => {
    document.body.classList.remove(...THEME_CLASSES);
    document.body.classList.add(theme);
    document.documentElement.style.colorScheme = THEMES.find(({ id }) => id === theme).mode;
    try { localStorage.setItem('synth-theme', theme); }
    catch { /* Theme changes still work when browser storage is unavailable. */ }
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme: (value) => updateTheme(resolveTheme(value)), availableThemes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useTheme = () => useContext(ThemeContext);
