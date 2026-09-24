import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

export default function KingsWeekWidget() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedArticle, setSelectedArticle] = useState(null);

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
    const interval = setInterval(fetchKingsWeek, 30 * 60 * 1000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Keyboard escape to close modal
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setSelectedArticle(null);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  if (loading && !data) {
    return (
      <div className="flex-1 flex items-center justify-center gap-3 text-white/40 text-sm py-16">
        <div className="w-5 h-5 border-2 border-white/20 border-t-white/80 rounded-full animate-spin" />
        Loading King's Week...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white/40 text-sm gap-2 text-center p-8">
        <span className="text-3xl">📰</span>
        <span className="font-semibold text-white/60">King's Week is not available right now.</span>
        <span className="text-red-400 text-xs">{error || 'No data'}</span>
      </div>
    );
  }

  const articles = data.articles || [];
  const featureArticle = articles[0] || null;
  const gridArticles = articles.slice(1);

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto p-6 md:p-8 bg-[#000000] text-white">
      {/* Header Info */}
      <div className="flex justify-between items-center pb-4 mb-6 border-b border-[#1c1c1c]">
        <div>
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
            {data.title || "King's Week"}
          </h2>
          <p className="text-xs md:text-sm text-[#8a8a96] font-mono mt-1">
            {data.edition ? `${data.edition} • ` : ''}{data.date || ''}
          </p>
        </div>
        {data.link && (
          <a
            href={data.link}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-mono uppercase tracking-wider text-[#d0d0d0] hover:text-white border border-[#2a2a2a] hover:border-white px-4 py-1.5 rounded-full transition-all"
          >
            Full Edition ↗
          </a>
        )}
      </div>

      {/* Main Grid */}
      <div className="flex flex-col gap-5 max-w-6xl mx-auto w-full pb-12">
        {/* Feature Story Card */}
        {featureArticle && (
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            onClick={() => setSelectedArticle(featureArticle)}
            className="relative rounded-2xl overflow-hidden cursor-pointer min-h-[260px] md:min-h-[320px] flex flex-col justify-end p-6 md:p-8 bg-[#0c0c12] border border-white/10 hover:border-white/40 transition-all group shadow-2xl"
          >
            {featureArticle.imageUrl && (
              <div
                className="absolute inset-0 bg-cover bg-center transition-transform duration-700 group-hover:scale-105 opacity-70 group-hover:opacity-85"
                style={{ backgroundImage: `url(${featureArticle.imageUrl})` }}
              />
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-[#05050b] via-[#05050b]/75 to-transparent" />

            <div className="relative z-10 flex flex-col gap-2">
              <span className="text-[10px] md:text-xs font-bold font-mono tracking-widest text-[#d0d0d0] uppercase">
                FEATURE STORY • {featureArticle.date || data.date}
              </span>
              <h3 className="text-2xl md:text-4xl font-extrabold text-white leading-tight">
                {featureArticle.title}
              </h3>
              {featureArticle.summary && (
                <p className="text-sm md:text-base text-[#c9c9d4] max-w-3xl line-clamp-2 mt-1">
                  {featureArticle.summary}
                </p>
              )}
            </div>
          </motion.div>
        )}

        {/* 2-Column Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {gridArticles.map((article, idx) => (
            <motion.div
              key={article.id || idx}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: idx * 0.04 }}
              onClick={() => setSelectedArticle(article)}
              className="relative rounded-xl overflow-hidden cursor-pointer min-h-[170px] flex flex-col justify-end p-5 bg-[#0c0c12] border border-white/10 hover:border-white/40 transition-all group"
            >
              {article.imageUrl && (
                <div
                  className="absolute inset-0 bg-cover bg-center transition-transform duration-600 group-hover:scale-105 opacity-65 group-hover:opacity-80"
                  style={{ backgroundImage: `url(${article.imageUrl})` }}
                />
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-[#030308] via-[#030308]/80 to-transparent" />

              <div className="relative z-10 flex flex-col gap-1.5">
                {(article.author || article.date) && (
                  <span className="text-[10px] font-bold font-mono tracking-wider text-[#a0a0a8] uppercase">
                    {[article.author, article.date].filter(Boolean).join(' • ')}
                  </span>
                )}
                <h4 className="text-lg md:text-xl font-bold text-white leading-snug line-clamp-2">
                  {article.title}
                </h4>
                {article.summary && (
                  <p className="text-xs text-[#b0b0ba] line-clamp-2 mt-0.5">
                    {article.summary}
                  </p>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Reader Modal */}
      <AnimatePresence>
        {selectedArticle && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-8 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="relative w-full max-w-3xl max-h-[85vh] bg-[#07070c] border border-white/20 rounded-2xl overflow-hidden shadow-2xl flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header / Close bar */}
              <div className="flex justify-between items-center px-6 py-4 border-b border-white/10 shrink-0">
                <span className="text-xs font-mono tracking-wider text-[#8a8a96] uppercase">
                  KING'S HIGH SCHOOL
                </span>
                <button
                  onClick={() => setSelectedArticle(null)}
                  className="text-xs font-mono uppercase tracking-wider text-[#8f8f8f] hover:text-white border border-[#2a2a2a] hover:border-white px-3 py-1 rounded-full transition-all"
                >
                  ESC / CLOSE ✕
                </button>
              </div>

              {/* Scrollable Story Content */}
              <div className="overflow-y-auto p-6 md:p-8 flex flex-col gap-5">
                {selectedArticle.largeImageUrl || selectedArticle.imageUrl ? (
                  <img
                    src={selectedArticle.largeImageUrl || selectedArticle.imageUrl}
                    alt={selectedArticle.title}
                    className="w-full max-h-[340px] object-cover rounded-xl border border-white/10"
                  />
                ) : null}

                <div>
                  <h2 className="text-2xl md:text-3xl font-extrabold text-white leading-tight">
                    {selectedArticle.title}
                  </h2>
                  {(selectedArticle.author || selectedArticle.date) && (
                    <p className="text-xs font-mono text-[#8a8a96] tracking-wider uppercase mt-2">
                      {[selectedArticle.author, selectedArticle.date].filter(Boolean).join(' • ')}
                    </p>
                  )}
                </div>

                <div className="text-sm md:text-base text-[#d6d6de] leading-relaxed whitespace-pre-line space-y-4">
                  {selectedArticle.body || selectedArticle.summary || 'No article text available.'}
                </div>

                {selectedArticle.link && (
                  <div className="pt-4 border-t border-white/10">
                    <a
                      href={selectedArticle.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[#d0d0d0] hover:text-white border border-[#333333] hover:border-white px-5 py-2.5 rounded-full transition-all"
                    >
                      Read original story on Hail ↗
                    </a>
                  </div>
                )}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
