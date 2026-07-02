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
    <a
      href={data.link}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        flex: 1,
        display: 'block',
        borderRadius: '14px',
        overflow: 'hidden',
        position: 'relative',
        backgroundImage: `url(${data.imageUrl})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        textDecoration: 'none',
        cursor: 'pointer',
        minHeight: '120px',
        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.transform = 'scale(1.01)';
        e.currentTarget.style.boxShadow = '0 8px 32px rgba(0,0,0,0.5)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = 'scale(1)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      {/* Gradient overlay */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.35) 50%, rgba(0,0,0,0.1) 100%)',
      }} />

      {/* Content */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        padding: '16px',
        color: '#ffffff',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span style={{
            padding: '2px 10px',
            borderRadius: '20px',
            background: 'rgba(109,40,217,0.85)',
            fontSize: '0.7rem',
            fontWeight: '700',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            color: '#e9d5ff',
          }}>
            {data.edition}
          </span>
          <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.55)' }}>
            {data.date}
          </span>
        </div>
        <div style={{
          fontSize: 'clamp(0.85rem, 1.1vw, 1rem)',
          fontWeight: '600',
          lineHeight: 1.3,
          color: '#ffffff',
          textShadow: '0 1px 8px rgba(0,0,0,0.8)',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>
          {data.title}
        </div>
      </div>

      {/* Read Issue badge — top right */}
      <div style={{
        position: 'absolute', top: '12px', right: '12px',
        background: 'rgba(0,0,0,0.55)',
        backdropFilter: 'blur(8px)',
        padding: '4px 10px',
        borderRadius: '20px',
        fontSize: '0.7rem',
        color: 'rgba(255,255,255,0.8)',
        fontWeight: '500',
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
      }}>
        Read Issue
        <svg width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" strokeLinecap="round" strokeLinejoin="round"/>
          <polyline points="15 3 21 3 21 9" strokeLinecap="round" strokeLinejoin="round"/>
          <line x1="10" y1="14" x2="21" y2="3" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
    </a>
  );
}
