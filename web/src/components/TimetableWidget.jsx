export default function TimetableWidget() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      gap: '10px',
      opacity: 0.7,
    }}>
      <div style={{ fontSize: '1.5rem', fontWeight: 300, opacity: 0.4, letterSpacing: '0.1em' }}>[ ]</div>
      <div style={{ fontWeight: 600, fontSize: '0.95rem', letterSpacing: '0.05em' }}>Timetable</div>
      <div style={{
        fontSize: '0.75rem',
        textTransform: 'uppercase',
        letterSpacing: '0.2em',
        background: 'rgba(59, 130, 246, 0.2)',
        border: '1px solid rgba(59, 130, 246, 0.4)',
        padding: '4px 12px',
        borderRadius: '999px',
        color: '#93c5fd',
      }}>
        Coming Soon
      </div>
    </div>
  );
}
