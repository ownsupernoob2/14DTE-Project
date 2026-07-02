import { useState, useEffect } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

export default function KingsWeekWidget() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    
    const fetchKingsWeek = async () => {
      try {
        setLoading(true);
        const res = await fetch(`${API_URL}/api/kings-week`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const result = await res.json();
        
        if (mounted) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        console.error('Failed to fetch Kings Week:', err);
        if (mounted) setError(err.message);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchKingsWeek();
    
    // Refresh every 30 minutes
    const interval = setInterval(fetchKingsWeek, 30 * 60 * 1000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  if (loading && !data) {
    return (
      <div className="glass-panel w-full h-full rounded-2xl flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="glass-panel w-full h-full rounded-2xl flex items-center justify-center flex-col p-4 text-center">
        <div className="text-[var(--text-secondary)] mb-2">King's Week</div>
        <div className="text-[var(--status-error)] text-sm">{error || 'No data available'}</div>
      </div>
    );
  }

  return (
    <a 
      href={data.link} 
      target="_blank" 
      rel="noopener noreferrer"
      className="block w-full h-full rounded-2xl overflow-hidden relative group cursor-pointer"
      style={{
        backgroundImage: `url(${data.imageUrl})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        textDecoration: 'none'
      }}
    >
      {/* Dark overlay for text readability */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent transition-opacity group-hover:opacity-90"></div>
      
      <div className="absolute bottom-0 left-0 p-6 w-full text-white">
        <div className="flex items-center gap-3 mb-1">
          <div className="px-3 py-1 rounded-full bg-[var(--accent-color)] text-white text-sm font-semibold shadow-lg">
            {data.edition}
          </div>
          <div className="text-sm text-gray-300 font-medium">
            {data.date}
          </div>
        </div>
        
        <h3 className="text-2xl font-bold leading-tight line-clamp-2 drop-shadow-md">
          {data.title}
        </h3>
      </div>
      
      {/* Read indicator */}
      <div className="absolute top-4 right-4 bg-black/50 backdrop-blur-md px-3 py-1.5 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
        <span className="text-sm font-medium text-white flex items-center gap-1">
          Read Issue 
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
        </span>
      </div>
    </a>
  );
}
