import React, { useState, useRef, useEffect } from 'react';
import WidgetContainer from '../components/WidgetContainer';
import { useServerStatus } from '../contexts/ServerStatusContext';

const API_URL = import.meta.env.VITE_API_URL || 'https://api.smartmirror.me';

const Simulator = () => {
  const [scanState, setScanState] = useState('waiting'); // waiting, scanning, authenticated, error
  const [widgets, setWidgets] = useState([]);
  const [errorMsg, setErrorMsg] = useState('');
  const [winSize, setWinSize] = useState({ w: window.innerWidth, h: window.innerHeight });
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const { isServerUp } = useServerStatus();

  useEffect(() => {
    const handleResize = () => setWinSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    let stream = null;
    if (scanState === 'waiting') {
      navigator.mediaDevices.getUserMedia({ video: true })
        .then(s => {
          stream = s;
          if (videoRef.current) {
            videoRef.current.srcObject = s;
          }
        })
        .catch(err => console.error("Camera error:", err));
    }
    return () => {
      if (stream) {
        stream.getTracks().forEach(t => t.stop());
      }
    };
  }, [scanState]);

  const captureAndVerify = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const context = canvasRef.current.getContext('2d');
    context.drawImage(videoRef.current, 0, 0, 300, 225);
    const base64 = canvasRef.current.toDataURL('image/jpeg', 0.8);
    verifyFace(base64);
  };

  const bypassScan = () => {
    console.log("Developer bypass activated.");
    verifyFace("bypass");
  };

  const verifyFace = async (base64) => {
    setScanState('scanning');
    try {
      const res = await fetch(`${API_URL}/api/verify-face`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: base64 })
      });
      
      if (res.ok) {
        const data = await res.json();
        console.log("Simulator authenticated successfully. Data:", data);
        
        const fetched = data.widgets || []
        const normalized = fetched.map(w => {
          const wNew = { ...w }
          if (w.x !== undefined && w.x > 100) {
            wNew.x = (w.x / 1280) * 100
          }
          if (w.y !== undefined && w.y > 100) {
            wNew.y = (w.y / 800) * 100
          }
          if (w.w !== undefined && w.w > 100) {
            wNew.w = (w.w / 1280) * 100
          }
          if (w.h !== undefined && w.h > 100) {
            wNew.h = (w.h / 800) * 100
          }
          return wNew
        })
        
        setWidgets(normalized);
        setScanState('authenticated');
      } else {
        console.error("Authentication failed:", res.status);
        setScanState('error');
        setErrorMsg('Face not recognised');
        setTimeout(() => setScanState('waiting'), 3000);
      }
    } catch (err) {
      console.error("Server connection error during verification:", err);
      setScanState('error');
      setErrorMsg('Server error');
      setTimeout(() => setScanState('waiting'), 3000);
    }
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
      {scanState === 'waiting' && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
          <video ref={videoRef} autoPlay playsInline muted style={{ width: '300px', borderRadius: '12px', transform: 'scaleX(-1)' }} />
          <canvas ref={canvasRef} width="300" height="225" style={{ display: 'none' }} />
          <button onClick={captureAndVerify} style={{ padding: '10px 20px', borderRadius: '8px', background: '#3b82f6', color: 'white', border: 'none', cursor: 'pointer' }}>Scan Face</button>
          <button onClick={bypassScan} style={{ padding: '8px 16px', borderRadius: '8px', background: 'transparent', border: '1px solid #666', color: '#ccc', cursor: 'pointer', fontSize: '0.8rem' }}>Developer Bypass</button>
        </div>
      )}

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
              containerWidth={winSize.w}
              containerHeight={winSize.h}
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
