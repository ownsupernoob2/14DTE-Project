import React, { useState, useRef, useEffect } from 'react';
import WidgetContainer from '../components/WidgetContainer';
import { useServerStatus } from '../contexts/ServerStatusContext';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

const Simulator = () => {
  const [scanState, setScanState] = useState('waiting'); // waiting, scanning, authenticated, error
  const [widgets, setWidgets] = useState([]);
  const [errorMsg, setErrorMsg] = useState('');
  const fileInputRef = useRef(null);
  const { isServerUp } = useServerStatus();

  useEffect(() => {
    // Add a keyboard listener to trigger the file input
    const handleKeyDown = (e) => {
      if (e.key === 'v') {
        fileInputRef.current?.click();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (event) => {
      const base64 = event.target.result;
      setScanState('scanning');
      try {
        const res = await fetch(`${API_URL}/api/verify-face`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: base64 })
        });
        
        if (res.ok) {
          const data = await res.json();
          setWidgets(data.widgets || []);
          setScanState('authenticated');
        } else {
          setScanState('error');
          setErrorMsg('Face not recognised');
          setTimeout(() => setScanState('waiting'), 3000);
        }
      } catch (err) {
        setScanState('error');
        setErrorMsg('Server error');
        setTimeout(() => setScanState('waiting'), 3000);
      }
    };
    reader.readAsDataURL(file);
  };

  return (
    <div style={{
      backgroundColor: 'black',
      color: 'white',
      height: '100vh',
      width: '100vw',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Hidden file input for dev testing */}
      <input 
        type="file" 
        ref={fileInputRef} 
        style={{ display: 'none' }} 
        accept="image/*"
        onChange={handleFileChange}
      />

      {/* Connection indicator */}
      {!isServerUp && (
        <div style={{ position: 'absolute', bottom: 10, left: 10, width: 8, height: 8, borderRadius: '50%', backgroundColor: 'red', opacity: 0.5 }} />
      )}

      {scanState === 'scanning' && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', opacity: 0.5 }}>
          <p style={{ animation: 'pulse 1s infinite' }}>Recognising...</p>
        </div>
      )}

      {scanState === 'error' && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#ff4444' }}>
          <p>{errorMsg}</p>
        </div>
      )}

      {scanState === 'authenticated' && (
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
          {widgets.map(w => (
            <WidgetContainer 
              key={w.id} 
              widget={w} 
              readonly={true} 
              onRemove={() => {}} 
              onMove={() => {}} 
            />
          ))}
        </div>
      )}

      <style>
        {`
          @keyframes pulse {
            0% { opacity: 0.5; }
            50% { opacity: 1; }
            100% { opacity: 0.5; }
          }
        `}
      </style>
    </div>
  );
};

export default Simulator;
