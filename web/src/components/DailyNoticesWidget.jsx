import { useEffect, useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

export default function DailyNoticesWidget() {
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterQuery, setFilterQuery] = useState(localStorage.getItem('notices_filter') || '');

  useEffect(() => {
    const fetchNotices = async () => {
      try {
        const today = new Date().toDateString();
        const cachedDate = localStorage.getItem('notices_date');
        const cachedData = localStorage.getItem('notices_data');

        if (cachedDate === today && cachedData) {
          setNotices(JSON.parse(cachedData));
          setLoading(false);
          return;
        }

        const res = await fetch(`${API_URL}/api/notices`);
        if (!res.ok) throw new Error('Notices not found/failed to load');
        const data = await res.json();

        if (Array.isArray(data)) {
          setNotices(data);
          localStorage.setItem('notices_date', today);
          localStorage.setItem('notices_data', JSON.stringify(data));
        } else {
          setNotices([]);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchNotices();
  }, []);

  const handleFilterChange = (e) => {
    const val = e.target.value;
    setFilterQuery(val);
    localStorage.setItem('notices_filter', val);
  };

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', opacity: 0.7, padding: '8px' }}>
      <div className="notices-spinner" />
      <span>Loading notices...</span>
    </div>
  );
  if (error) return <div style={{ color: '#f87171', padding: '8px', fontSize: '0.8rem' }}>⚠️ {error}</div>;
  if (notices.length === 0) return <div style={{ opacity: 0.5, padding: '8px', fontStyle: 'italic', fontSize: '0.85rem' }}>No notices today.</div>;

  // Filter notices
  const lowerFilter = filterQuery.toLowerCase();
  const filteredNotices = notices.filter(n => {
    if (!filterQuery) return true;
    return (n.category && n.category.toLowerCase().includes(lowerFilter)) ||
           (n.notice && n.notice.toLowerCase().includes(lowerFilter));
  });

  // Group notices by category
  const groupedNotices = filteredNotices.reduce((acc, notice) => {
    const cat = notice.category || 'General';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(notice.notice);
    return acc;
  }, {});

  const containsHTML = (str) => /<[a-z][\s\S]*>/i.test(str);

  return (
    <div className="widget-notices">
      {/* Filter input */}
      <div style={{ padding: '2px 0 10px' }}>
        <input
          type="text"
          placeholder="🔍 Filter notices..."
          value={filterQuery}
          onChange={handleFilterChange}
          className="notices-filter-input"
        />
      </div>

      {/* Notices list */}
      <div className="notices-scroll-area">
        {filteredNotices.length === 0 ? (
          <div style={{ opacity: 0.5, fontStyle: 'italic', fontSize: '0.85rem' }}>No matches found.</div>
        ) : (
          Object.entries(groupedNotices).map(([category, items], idx) => (
            <div key={idx} className="notice-category-group">
              <div className="notice-category-label">{category}</div>
              {items.map((item, i) => (
                containsHTML(item) ? (
                  // Render HTML tables safely
                  <div
                    key={i}
                    className="notice-table-wrapper"
                    dangerouslySetInnerHTML={{ __html: item }}
                  />
                ) : (
                  <p key={i} className="notice-text">{item}</p>
                )
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}