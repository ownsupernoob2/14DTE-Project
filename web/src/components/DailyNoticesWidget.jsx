import { useEffect, useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

// Helper to extract clean summary details from raw HTML/text
const extractDetails = (html) => {
  const details = {};
  if (!html) return details;
  
  // Clean HTML tags first to scan pure text
  const text = html.replace(/<[^>]*>/g, ' ');
  
  // Date: e.g. "21 May", "Monday 21st", "Friday 4th June"
  const dateMatch = text.match(/\b\d{1,2}(st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b/i) ||
                    text.match(/\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b/i);
  
  // Time: e.g. "12:30pm", "9.00am", "14:00"
  const timeMatch = text.match(/\b\d{1,2}([:.]\d{2})?\s*(am|pm)\b/i) || 
                    text.match(/\b\d{1,2}[:.]\d{2}\b/);
  
  // Room/Location: e.g. "Room 4", "Rm 12", "Library", "Gym", "Main Field"
  const roomMatch = text.match(/\b(Room|Rm|Classroom)\s+([A-Za-z0-9-]+)\b/i) || 
                    text.match(/\b(Library|Auditorium|Hall|Gym|Field|Pool|Music Suite|Performing Arts Centre)\b/i);
  
  if (dateMatch) details.date = dateMatch[0].trim();
  if (timeMatch) details.time = timeMatch[0].trim();
  if (roomMatch) details.location = roomMatch[0].trim();
  
  return details;
};

export default function DailyNoticesWidget() {
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Local filter search query
  const [filterQuery, setFilterQuery] = useState(localStorage.getItem('notices_filter') || '');

  // User Preferences
  const [yearLevel, setYearLevel] = useState(() => localStorage.getItem('notices_year_level') || 'All');
  const [classCodes, setClassCodes] = useState(() => localStorage.getItem('notices_class_codes') || '');
  const [focusMode, setFocusMode] = useState(() => localStorage.getItem('notices_focus_mode') === 'true');
  const [visibleCategories, setVisibleCategories] = useState(() => {
    const cached = localStorage.getItem('notices_visible_categories');
    return cached ? JSON.parse(cached) : ['General', 'Sports', 'Meetings', 'Careers', 'Academic'];
  });
  
  // Pinned Notice state
  const [pinnedIds, setPinnedIds] = useState(() => {
    const cached = localStorage.getItem('notices_pinned');
    return cached ? JSON.parse(cached) : [];
  });

  const [showSettings, setShowSettings] = useState(false);
  const [activeTab, setActiveTab] = useState('All');

  // Load notices from API
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

  // Save Preferences to localStorage
  useEffect(() => {
    localStorage.setItem('notices_year_level', yearLevel);
  }, [yearLevel]);

  useEffect(() => {
    localStorage.setItem('notices_class_codes', classCodes);
  }, [classCodes]);

  useEffect(() => {
    localStorage.setItem('notices_focus_mode', String(focusMode));
  }, [focusMode]);

  useEffect(() => {
    localStorage.setItem('notices_visible_categories', JSON.stringify(visibleCategories));
  }, [visibleCategories]);

  useEffect(() => {
    localStorage.setItem('notices_pinned', JSON.stringify(pinnedIds));
  }, [pinnedIds]);

  const handleFilterChange = (e) => {
    const val = e.target.value;
    setFilterQuery(val);
    localStorage.setItem('notices_filter', val);
  };

  // Get dynamic categories list from fetched data
  const defaultCategories = ['General', 'Sports', 'Meetings', 'Careers', 'Academic'];
  const parsedCategories = Array.from(new Set(notices.map(n => n.category || 'General')));
  const allCategories = Array.from(new Set([...defaultCategories, ...parsedCategories]));

  // Parse & Enrich Notices for backward compatibility
  const enrichedNotices = notices.map((n, idx) => {
    const id = n.id || `notice-${idx}-${(n.title || '').substring(0, 10)}-${(n.notice || '').substring(0, 10)}`;
    const category = n.category || 'General';
    
    // Fallback title: extract first sentence from the notice text if title not present
    const cleanText = n.notice ? n.notice.replace(/<[^>]*>/g, ' ') : '';
    const firstSentence = cleanText.split(/[.!?\n]/)[0] || '';
    const title = n.title || (firstSentence.length > 5 && firstSentence.length < 60 ? firstSentence.trim() : `${category} Update`);

    // Target Year levels parsing if missing
    let targetYears = [];
    if (n.targetYears && Array.isArray(n.targetYears)) {
      targetYears = n.targetYears;
    } else {
      const textToScan = ((n.title || '') + ' ' + (n.notice || '')).toLowerCase();
      if (textToScan.includes('all years') || textToScan.includes('every year')) {
        targetYears = ['All'];
      } else {
        for (let y = 9; y <= 13; y++) {
          if (new RegExp(`\\b(year|yr|y)\\s*${y}\\b`, 'i').test(textToScan)) {
            targetYears.push(String(y));
          }
        }
        if (targetYears.length === 0) {
          targetYears = ['All'];
        }
      }
    }

    // Importance parsing
    let importance = n.importance || 'normal';
    if (!n.importance && n.notice) {
      const textToScan = ((n.title || '') + ' ' + (n.notice || '')).toLowerCase();
      if (textToScan.includes('urgent') || textToScan.includes('room change') || textToScan.includes('cancelled') || textToScan.includes('important')) {
        importance = 'high';
      }
    }

    // Contact extraction
    let contact = n.contact || '';
    if (!n.contact && n.notice) {
      const match = n.notice.match(/\b(Mr|Mrs|Ms|Miss|Dr|Msr)\s+[A-Z][a-zA-Z]+/);
      if (match) {
        contact = match[0];
      }
    }

    return {
      ...n,
      id,
      title,
      category,
      targetYears,
      importance,
      contact
    };
  });

  // Split and clean user input class codes
  const userClasses = classCodes
    .split(',')
    .map(c => c.trim())
    .filter(c => c.length > 0);

  // Match class codes inside a notice
  const isClassMatched = (notice) => {
    if (userClasses.length === 0) return false;
    const textToScan = ((notice.title || '') + ' ' + (notice.notice || '')).toLowerCase();
    return userClasses.some(cls => new RegExp(`\\b${cls.toLowerCase()}\\b`).test(textToScan));
  };

  // Check if a notice is "For Me"
  const isForMe = (notice) => {
    const matchesYear = yearLevel === 'All' || notice.targetYears.includes('All') || notice.targetYears.includes(yearLevel);
    const matchesClass = isClassMatched(notice);
    
    // Notice is for me if it matches my year level OR specifically mentions my class code
    return matchesYear || matchesClass;
  };

  // Toggle Category Checkbox helper
  const handleCategoryToggle = (cat) => {
    if (visibleCategories.includes(cat)) {
      setVisibleCategories(visibleCategories.filter(c => c !== cat));
    } else {
      setVisibleCategories([...visibleCategories, cat]);
    }
  };

  // Filtering notices
  const filteredNotices = enrichedNotices.filter(n => {
    // 1. Search Query filter
    if (filterQuery) {
      const lowerQuery = filterQuery.toLowerCase();
      const matchesSearch = 
        (n.title && n.title.toLowerCase().includes(lowerQuery)) ||
        (n.category && n.category.toLowerCase().includes(lowerQuery)) ||
        (n.contact && n.contact.toLowerCase().includes(lowerQuery)) ||
        (n.notice && n.notice.toLowerCase().includes(lowerQuery));
      if (!matchesSearch) return false;
    }

    // 2. Tab Filter
    if (activeTab === 'Pinned') {
      return pinnedIds.includes(n.id);
    }

    // 3. Category Checklist filter (pinned notices bypass category hiding)
    if (!visibleCategories.includes(n.category)) {
      return false;
    }

    // 4. Tab Specific criteria
    if (activeTab === 'For Me') {
      if (!isForMe(n)) return false;
    } else if (activeTab === 'Sports') {
      if (n.category.toLowerCase() !== 'sports') return false;
    } else if (activeTab === 'Meetings') {
      if (n.category.toLowerCase() !== 'meetings') return false;
    }

    // 5. Focus Mode Filter (applies to other tabs when enabled)
    if (focusMode && activeTab !== 'For Me') {
      if (!isForMe(n)) return false;
    }

    return true;
  });

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', opacity: 0.7, padding: '8px' }}>
      <div className="notices-spinner" />
      <span>Loading notices...</span>
    </div>
  );

  if (error) return <div style={{ color: '#f87171', padding: '8px', fontSize: '0.8em' }}>[Error] {error}</div>;
  if (notices.length === 0) return <div style={{ opacity: 0.5, padding: '8px', fontStyle: 'italic', fontSize: '0.85em' }}>No notices today.</div>;

  return (
    <div className="widget-notices">
      {/* Top Search & Settings Toggle Row */}
      <div className="notices-search-row">
        <input
          type="text"
          placeholder="Filter notices..."
          value={filterQuery}
          onChange={handleFilterChange}
          className="notices-filter-input"
          style={{ flex: 1 }}
        />
        <button
          className={`settings-toggle-btn ${showSettings ? 'active' : ''}`}
          onClick={() => setShowSettings(!showSettings)}
          title="Notice settings"
          style={{ fontSize: '0.75em', padding: '4px 8px' }}
        >
          Settings
        </button>
      </div>

      {/* Settings Drawer */}
      {showSettings && (
        <div className="settings-drawer">
          <div className="settings-group">
            <label>Year Level</label>
            <select value={yearLevel} onChange={(e) => setYearLevel(e.target.value)}>
              <option value="All">All Years</option>
              <option value="9">Year 9</option>
              <option value="10">Year 10</option>
              <option value="11">Year 11</option>
              <option value="12">Year 12</option>
              <option value="13">Year 13</option>
            </select>
          </div>

          <div className="settings-group">
            <label>Form Class / Class Codes</label>
            <input
              type="text"
              placeholder="e.g. 9SR, 9CR"
              value={classCodes}
              onChange={(e) => setClassCodes(e.target.value)}
            />
          </div>

          <div className="settings-toggle-row">
            <label style={{ fontSize: '0.75em', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
              Focus Mode
            </label>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={focusMode}
                onChange={(e) => setFocusMode(e.target.checked)}
              />
              <span className="slider"></span>
            </label>
          </div>

          <div className="settings-group">
            <label>Visible Categories</label>
            <div className="categories-checklist">
              {allCategories.map(cat => (
                <label key={cat}>
                  <input
                    type="checkbox"
                    checked={visibleCategories.includes(cat)}
                    onChange={() => handleCategoryToggle(cat)}
                  />
                  <span>{cat}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Sleek Category Navigation Tabs */}
      <div className="notices-tabs-row">
        <div className="notices-tabs">
          <button
            className={`notices-tab ${activeTab === 'All' ? 'active' : ''}`}
            onClick={() => setActiveTab('All')}
          >
            All
          </button>
          <button
            className={`notices-tab ${activeTab === 'Pinned' ? 'active' : ''}`}
            onClick={() => setActiveTab('Pinned')}
          >
            Pinned
          </button>
          <button
            className={`notices-tab ${activeTab === 'For Me' ? 'active' : ''}`}
            onClick={() => setActiveTab('For Me')}
          >
            For Me
          </button>
          <button
            className={`notices-tab ${activeTab === 'Sports' ? 'active' : ''}`}
            onClick={() => setActiveTab('Sports')}
          >
            Sports
          </button>
          <button
            className={`notices-tab ${activeTab === 'Meetings' ? 'active' : ''}`}
            onClick={() => setActiveTab('Meetings')}
          >
            Meetings
          </button>
        </div>
      </div>

      {/* Discrete Card-based Scrolling List */}
      <div className="notices-scroll-area">
        {filteredNotices.length === 0 ? (
          <div style={{ opacity: 0.5, fontStyle: 'italic', fontSize: '0.85em', padding: '16px 0', textAlign: 'center' }}>
            No matches found.
          </div>
        ) : (
          filteredNotices.map((n) => {
            const isPinned = pinnedIds.includes(n.id);
            const isMatched = isClassMatched(n);
            const details = extractDetails(n.notice || '');

            return (
              <div
                key={n.id}
                className={`notice-card ${n.importance === 'high' ? 'urgent' : ''} ${isMatched ? 'class-matched' : ''}`}
              >
                {/* Header elements: badges and pin */}
                <div className="notice-card-header">
                  <div className="notice-badges">
                    <span className={`notice-badge-category category-${n.category.toLowerCase()}`}>
                      {n.category}
                    </span>
                    {n.targetYears && n.targetYears.map(year => (
                      <span key={year} className="notice-badge-year">
                        Y{year}
                      </span>
                    ))}
                    {n.importance === 'high' && (
                      <span className="notice-badge-urgent">
                        URGENT
                      </span>
                    )}
                    {isMatched && (
                      <span className="notice-badge-class-warning">
                        Class Update
                      </span>
                    )}
                  </div>

                  <button
                    className={`notice-pin-btn ${isPinned ? 'pinned' : ''}`}
                    onClick={() => {
                      if (isPinned) {
                        setPinnedIds(pinnedIds.filter(id => id !== n.id));
                      } else {
                        setPinnedIds([...pinnedIds, n.id]);
                      }
                    }}
                    title={isPinned ? "Unpin notice" : "Pin notice"}
                    style={{ fontSize: '0.75em', padding: '2px 6px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px' }}
                  >
                    {isPinned ? 'Unpin' : 'Pin'}
                  </button>
                </div>

                {/* Title */}
                <h3 className="notice-card-title">{n.title}</h3>

                {/* Pinned Shelf details callout */}
                {isPinned && (details.date || details.time || details.location) && (
                  <div className="pinned-summary-shelf">
                    {details.date && (
                      <div className="summary-item">
                        <span className="summary-text">Date: {details.date}</span>
                      </div>
                    )}
                    {details.time && (
                      <div className="summary-item">
                        <span className="summary-text">Time: {details.time}</span>
                      </div>
                    )}
                    {details.location && (
                      <div className="summary-item">
                        <span className="summary-text">Room: {details.location}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Content */}
                <div
                  className="notice-card-body"
                  dangerouslySetInnerHTML={{ __html: n.notice }}
                />

                {/* Contact person badge */}
                {n.contact && (
                  <div className="notice-card-footer">
                    <span className="notice-contact">
                      Contact: {n.contact}
                    </span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}