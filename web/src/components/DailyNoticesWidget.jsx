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


  if (loading) return <div className="widget-notices-loading">Loading notices...</div>;
  if (error) return <div className="widget-notices-error">{error}</div>;
  if (notices.length === 0) return <div className="widget-notices-empty">No notices today.</div>;

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

  return (
    <div className="widget-notices" style={{ display: 'flex', flexDirection: 'column', height: '100%', fontSize: '0.85rem' }}>
      <input 
        type="text" 
        placeholder="Filter notices (e.g. Student Council)" 
        value={filterQuery}
        onChange={handleFilterChange}
        style={{ marginBottom: '8px', padding: '4px', borderRadius: '4px', border: '1px solid #ccc', fontSize: '0.8rem', background: 'rgba(0,0,0,0.2)', color: 'white' }}
      />
      <div style={{ overflowY: 'auto', textAlign: 'left', flex: 1 }}>
        {filteredNotices.length === 0 ? (
          <div style={{ opacity: 0.7, fontStyle: 'italic' }}>No matches found.</div>
        ) : (
          Object.entries(groupedNotices).map(([category, items], idx) => (
            <div key={idx} className="notice-category-group" style={{ marginBottom: '8px' }}>
              <strong style={{ display: 'block', color: 'var(--accent-color, #4a90e2)', marginBottom: '4px' }}>{category}</strong>
              <ul style={{ margin: 0, paddingLeft: '16px' }}>
                {items.map((item, i) => (
                  <li key={i} style={{ marginBottom: '4px' }}>{item}</li>
                ))}
              </ul>
            </div>
          ))
        )}
      </div>
    </div>
  );
}