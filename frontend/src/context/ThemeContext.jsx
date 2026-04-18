import React, { createContext, useContext, useEffect, useState } from 'react';

const ThemeContext = createContext();

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('synth-theme') || 'theme-cyberpunk';
    }
    return 'theme-cyberpunk';
  });

  useEffect(() => {
    // Remove all previous theme classes
    document.body.classList.remove(
      'theme-cyberpunk',
      'theme-vaporwave',
      'theme-nord',
      'theme-dark-elegance',
      'theme-light-mode'
    );
    // Add the new theme class
    document.body.classList.add(theme);
    localStorage.setItem('synth-theme', theme);
  }, [theme]);

  // Expose an array of available themes so the picker can render them dynamically.
  const availableThemes = [
    { id: 'theme-cyberpunk', name: 'Cyberpunk' },
    { id: 'theme-vaporwave', name: 'Vaporwave' },
    { id: 'theme-nord', name: 'Nord' },
    { id: 'theme-dark-elegance', name: 'Dark' },
    { id: 'theme-light-mode', name: 'Light' }
  ];

  return (
    <ThemeContext.Provider value={{ theme, setTheme, availableThemes }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
