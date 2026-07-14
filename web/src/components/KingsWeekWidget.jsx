import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

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
        if (mounted) { setData(result); setError(null); }
      } catch (err) {
        console.error('Failed to fetch Kings Week:', err);
        if (mounted) setError(err.message);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchKingsWeek();
    const interval = setInterval(fetchKingsWeek, 30 * 60 * 1000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  if (loading && !data) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '12px',
        color: 'rgba(255,255,255,0.4)',
        fontSize: '0.85rem',
      }}>
        <div style={{
          width: '20px', height: '20px',
          border: '2px solid rgba(255,255,255,0.15)',
          borderTopColor: 'rgba(255,255,255,0.6)',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }} />
        Loading King's Week...
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'rgba(255,255,255,0.35)',
        fontSize: '0.8rem',
        gap: '6px',
        textAlign: 'center',
        padding: '12px',
      }}>
        <span style={{ fontSize: '1.5rem' }}>📰</span>
        <span>King's Week</span>
        <span style={{ color: '#f87171', fontSize: '0.75rem' }}>{error || 'No data'}</span>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      className="glass-panel rounded-xl flex-1 flex flex-col overflow-hidden relative group cursor-pointer"
      onClick={() => data.link && window.open(data.link, '_blank', 'noopener,noreferrer')}
    >
      <div className="absolute inset-0 z-0 overflow-hidden">
        {/* Featured image with zoom effect on hover */}
        <motion.div
          className="bg-cover bg-center w-full h-full opacity-70 mix-blend-luminosity"
          style={{ backgroundImage: `url(${data.imageUrl})` }}
          whileHover={{ scale: 1.05 }}
          transition={{ duration: 0.6 }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-surface-dim via-surface-dim/80 to-transparent" />
      </div>

      <div className="relative z-10 p-6 flex flex-col h-full justify-end flex-1 select-none">
        <span className="bg-primary text-on-primary px-3 py-1 rounded-full font-label-caps text-xs self-start mb-4 shadow-[0_0_10px_rgba(77,142,255,0.5)] uppercase tracking-wider font-bold">
          Featured News
        </span>
        
        <div className="mb-2">
          <span className="font-label-caps text-xs text-primary-fixed-dim bg-primary/20 px-2 py-0.5 rounded mr-2">
            {data.edition || "King's Week"}
          </span>
          <span className="font-label-caps text-xs text-outline">
            {data.date}
          </span>
        </div>

        <h3 className="font-display-lg text-2xl md:text-3xl font-bold mb-2 text-white leading-tight">
          {data.title}
        </h3>
        
        <p className="font-body-lg text-sm text-on-surface-variant max-w-lg mb-6 line-clamp-3">
          Highlights from this week's inter-house competitions, academic achievements, and upcoming weekend fixtures.
        </p>

        <button className="bg-transparent border border-outline hover:bg-white/10 hover:border-white text-white font-label-caps text-xs px-6 py-2 rounded-full self-start transition-all duration-300 backdrop-blur-sm active:scale-95">
          Read Full Edition
        </button>
      </div>
    </motion.div>
  );
}
