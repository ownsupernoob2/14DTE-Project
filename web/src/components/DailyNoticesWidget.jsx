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

export default function DailyNoticesWidget({ widget = {}, onUpdateData, readonly = false }) {
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Local filter search query
  const [filterQuery, setFilterQuery] = useState(localStorage.getItem('notices_filter') || '');

  // User Preferences loaded from widget data or localStorage
  const [yearLevel, setYearLevel] = useState(() => widget.data?.yearLevel || localStorage.getItem('notices_year_level') || 'All');
  const [classCodes, setClassCodes] = useState(() => widget.data?.classCodes || localStorage.getItem('notices_class_codes') || '');
  const [focusMode, setFocusMode] = useState(() => {
    if (widget.data?.focusMode !== undefined) return widget.data.focusMode;
    return localStorage.getItem('notices_focus_mode') === 'true';
  });
  const [visibleCategories, setVisibleCategories] = useState(() => {
    if (widget.data?.visibleCategories) return widget.data.visibleCategories;
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

  // Sync state with widget.data changes (e.g. Server updates, Undo layout actions)
  useEffect(() => {
    if (widget.data) {
      if (widget.data.yearLevel !== undefined) setYearLevel(widget.data.yearLevel);
      if (widget.data.classCodes !== undefined) setClassCodes(widget.data.classCodes);
      if (widget.data.focusMode !== undefined) setFocusMode(widget.data.focusMode);
      if (widget.data.visibleCategories !== undefined) setVisibleCategories(widget.data.visibleCategories);
    }
  }, [widget.data]);

  // Keep pinned state saved in local storage
  useEffect(() => {
    localStorage.setItem('notices_pinned', JSON.stringify(pinnedIds));
  }, [pinnedIds]);

  const handleYearLevelChange = (val) => {
    setYearLevel(val);
    localStorage.setItem('notices_year_level', val);
    if (onUpdateData) {
      onUpdateData({ ...widget.data, yearLevel: val });
    }
  };

  const handleClassCodesChange = (val) => {
    setClassCodes(val);
    localStorage.setItem('notices_class_codes', val);
    if (onUpdateData) {
      onUpdateData({ ...widget.data, classCodes: val });
    }
  };

  const handleFocusModeChange = (val) => {
    setFocusMode(val);
    localStorage.setItem('notices_focus_mode', String(val));
    if (onUpdateData) {
      onUpdateData({ ...widget.data, focusMode: val });
    }
  };

  const handleCategoryToggle = (cat) => {
    const nextCats = visibleCategories.includes(cat)
      ? visibleCategories.filter(c => c !== cat)
      : [...visibleCategories, cat];
    setVisibleCategories(nextCats);
    localStorage.setItem('notices_visible_categories', JSON.stringify(nextCats));
    if (onUpdateData) {
      onUpdateData({ ...widget.data, visibleCategories: nextCats });
    }
  };

  const handleFilterChange = (e) => {
    const val = e.target.value;
    setFilterQuery(val);
    localStorage.setItem('notices_filter', val);
  };

  // Get dynamic categories list from notices
  const defaultCategories = ['General', 'Sports', 'Meetings', 'Careers', 'Academic'];
  const parsedCategories = Array.from(new Set(notices.map(n => n.category || 'General')));
  const allCategories = Array.from(new Set([...defaultCategories, ...parsedCategories]));

  // Parse & Enrich Notices for backward compatibility
  const enrichedNotices = notices.map((n, idx) => {
    const id = n.id || `notice-${idx}-${(n.title || '').substring(0, 10)}-${(n.notice || '').substring(0, 10)}`;
    const category = n.category || 'General';
    
    const cleanText = n.notice ? n.notice.replace(/<[^>]*>/g, ' ') : '';
    const firstSentence = cleanText.split(/[.!?\n]/)[0] || '';
    const title = n.title || (firstSentence.length > 5 && firstSentence.length < 60 ? firstSentence.trim() : `${category} Update`);

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

    let importance = n.importance || 'normal';
    if (!n.importance && n.notice) {
      const textToScan = ((n.title || '') + ' ' + (n.notice || '')).toLowerCase();
      if (textToScan.includes('urgent') || textToScan.includes('room change') || textToScan.includes('cancelled') || textToScan.includes('important')) {
        importance = 'high';
      }
    }

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

  const userClasses = classCodes
    .split(',')
    .map(c => c.trim())
    .filter(c => c.length > 0);

  const isClassMatched = (notice) => {
    if (userClasses.length === 0) return false;
    const textToScan = ((notice.title || '') + ' ' + (notice.notice || '')).toLowerCase();
    return userClasses.some(cls => new RegExp(`\\b${cls.toLowerCase()}\\b`).test(textToScan));
  };

  const isForMe = (notice) => {
    const matchesYear = yearLevel === 'All' || notice.targetYears.includes('All') || notice.targetYears.includes(yearLevel);
    const matchesClass = isClassMatched(notice);
    return matchesYear || matchesClass;
  };

  const filteredNotices = enrichedNotices.filter(n => {
    if (filterQuery) {
      const lowerQuery = filterQuery.toLowerCase();
      const matchesSearch = 
        (n.title && n.title.toLowerCase().includes(lowerQuery)) ||
        (n.category && n.category.toLowerCase().includes(lowerQuery)) ||
        (n.contact && n.contact.toLowerCase().includes(lowerQuery)) ||
        (n.notice && n.notice.toLowerCase().includes(lowerQuery));
      if (!matchesSearch) return false;
    }

    if (activeTab === 'Pinned') {
      return pinnedIds.includes(n.id);
    }

    if (!visibleCategories.includes(n.category)) {
      return false;
    }

    if (activeTab === 'For Me') {
      if (!isForMe(n)) return false;
    } else if (activeTab === 'Sports') {
      if (n.category.toLowerCase() !== 'sports') return false;
    } else if (activeTab === 'Meetings') {
      if (n.category.toLowerCase() !== 'meetings') return false;
    }

    if (focusMode && activeTab !== 'For Me') {
      if (!isForMe(n)) return false;
    }

    return true;
  });

  // Auto-scrolling effect for notices in readonly mode
  useEffect(() => {
    if (!readonly || loading || error || filteredNotices.length === 0) return;

    // Use a small timeout to let the DOM render completely
    const startScrollTimer = setTimeout(() => {
      const container = document.querySelector('.notices-scroll-area');
      if (!container) return;

      const scrollSpeed = 0.4; // pixels per step
      const intervalTime = 30; // ms
      const holdTime = 3000; // time to hold at top/bottom (ms)
      let holdTimer = null;
      let scrollInterval = null;

      const scroll = () => {
        if (!container) return;
        const maxScroll = container.scrollHeight - container.clientHeight;
        if (maxScroll <= 0) return;

        if (container.scrollTop >= maxScroll - 1) {
          clearInterval(scrollInterval);
          holdTimer = setTimeout(() => {
            // Smoothly slide back to top
            container.scrollTo({ top: 0, behavior: 'smooth' });
            holdTimer = setTimeout(() => {
              scrollInterval = setInterval(scroll, intervalTime);
            }, holdTime);
          }, holdTime);
        } else {
          container.scrollTop += scrollSpeed;
        }
      };

      // Start the scrolling cycle after initial delay
      holdTimer = setTimeout(() => {
        scrollInterval = setInterval(scroll, intervalTime);
      }, holdTime);

      // Clean up variables inside callback context
      return () => {
        if (scrollInterval) clearInterval(scrollInterval);
        if (holdTimer) clearTimeout(holdTimer);
      };
    }, 100);

    return () => clearTimeout(startScrollTimer);
  }, [readonly, loading, error, filteredNotices.length]);

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
      {/* Top Search & Settings Toggle Row - only in Edit Mode */}
      {!readonly && (
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
      )}

      {/* Settings Drawer - only in Edit Mode */}
      {!readonly && showSettings && (
        <div className="settings-drawer">
          <div className="settings-group">
            <label>Year Level</label>
            <select value={yearLevel} onChange={(e) => handleYearLevelChange(e.target.value)}>
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
              onChange={(e) => handleClassCodesChange(e.target.value)}
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
                onChange={(e) => handleFocusModeChange(e.target.checked)}
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

      {/* Sleek Category Navigation Tabs - only in Edit Mode */}
      {!readonly && (
        <div className="notices-tabs-row">
          <div className="notices-tabs">
            {['All', 'Pinned', 'For Me', 'Sports', 'Meetings'].map(tab => (
              <button
                key={tab}
                className={`notices-tab ${activeTab === tab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
      )}

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

                  {!readonly && (
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
                  )}
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