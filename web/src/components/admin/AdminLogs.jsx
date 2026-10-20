import React, { useState, useEffect, useRef } from 'react';

const LOG_TYPES = [
  { id: 'mirror', label: 'Mirror UI (mirror.log)' },
  { id: 'face', label: 'Face Daemon (face_daemon.log)' },
  { id: 'gesture', label: 'Gesture Daemon (gesture_daemon.log)' },
  { id: 'ffmpeg', label: 'FFmpeg Stream (ffmpeg.log)' },
  { id: 'rpicam', label: 'RPiCam Video (rpicam.log)' },
];

export default function AdminLogs({ token }) {
  const [activeLog, setActiveLog] = useState('mirror');
  const [logContent, setLogContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const logContainerRef = useRef(null);

  const fetchLogs = async (logName) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/logs?name=${logName}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Admin-Token': token,
        },
      });
      if (res.ok) {
        const data = await res.json();
        setLogContent(data.content || 'Log is empty.');
        setLastUpdated(data.updated);
      } else {
        setLogContent('Failed to fetch logs from server.');
      }
    } catch (err) {
      setLogContent(`Error fetching log: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs(activeLog);
  }, [activeLog]);

  // Auto-refresh interval (every 3 seconds)
  useEffect(() => {
    let interval = null;
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchLogs(activeLog);
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, activeLog]);

  // Auto-scroll terminal to bottom when content changes
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logContent]);

  return (
    <div style={{ padding: '20px', color: '#fff', backgroundColor: '#121212', borderRadius: '8px' }}>
      <h2>System Daemon Logs</h2>

      {/* Log Type Tabs */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
        {LOG_TYPES.map((log) => (
          <button
            key={log.id}
            onClick={() => setActiveLog(log.id)}
            style={{
              padding: '8px 16px',
              backgroundColor: activeLog === log.id ? '#0070f3' : '#333',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            {log.label}
          </button>
        ))}
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <div>
          <label style={{ cursor: 'pointer', fontSize: '14px' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              style={{ marginRight: '8px' }}
            />
            Auto-refresh (3s)
          </label>
        </div>
        <div style={{ fontSize: '12px', color: '#aaa' }}>
          {lastUpdated && `Last updated: ${new Date(lastUpdated).toLocaleTimeString()}`}
        </div>
      </div>

      {/* Terminal Container */}
      <pre
        ref={logContainerRef}
        style={{
          backgroundColor: '#000',
          color: '#00ff00',
          padding: '15px',
          borderRadius: '6px',
          height: '500px',
          overflowY: 'auto',
          fontFamily: 'monospace',
          fontSize: '13px',
          lineHeight: '1.4',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}
      >
        {loading && !logContent ? 'Loading...' : logContent}
      </pre>
    </div>
  );
}
