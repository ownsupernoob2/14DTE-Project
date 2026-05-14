import { createContext, useContext, useEffect, useState } from 'react';

const ServerStatusContext = createContext({ isServerUp: true, lastChecked: null });

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

export const ServerStatusProvider = ({ children }) => {
  const [isServerUp, setIsServerUp] = useState(true);
  const [lastChecked, setLastChecked] = useState(null);

  const checkStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/health`, { method: 'GET' });
      if (res.ok) {
        setIsServerUp(true);
      } else {
        setIsServerUp(false);
      }
    } catch (e) {
      setIsServerUp(false);
    } finally {
      setLastChecked(Date.now());
    }
  };

  useEffect(() => {
    checkStatus();

    // Check every 30 seconds
    const intervalId = setInterval(checkStatus, 30000);

    // Also check on window focus (redirect/refresh)
    const handleFocus = () => checkStatus();
    window.addEventListener('focus', handleFocus);

    return () => {
      clearInterval(intervalId);
      window.removeEventListener('focus', handleFocus);
    };
  }, []);

  return (
    <ServerStatusContext.Provider value={{ isServerUp, lastChecked, checkStatus }}>
      {children}
    </ServerStatusContext.Provider>
  );
};

export const useServerStatus = () => useContext(ServerStatusContext);
