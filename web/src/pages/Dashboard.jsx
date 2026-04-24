import { useState, useRef } from 'react'
import Navbar from '../components/Navbar'
import WidgetContainer from '../components/WidgetContainer'
import '../styles/dashboard.css'

export default function Dashboard() {
  const [widgets, setWidgets] = useState([])
  const [showAddMenu, setShowAddMenu] = useState(false)
  const containerRef = useRef(null)

  const addWidget = (type) => {
    const newWidget = {
      id: Date.now(),
      type,
      x: Math.random() * (containerRef.current?.offsetWidth - 200 || 300),
      y: Math.random() * (containerRef.current?.offsetHeight - 200 || 300),
    }
    setWidgets([...widgets, newWidget])
    setShowAddMenu(false)
  }

  const removeWidget = (id) => {
    setWidgets(widgets.filter((w) => w.id !== id))
  }

  const updateWidgetPosition = (id, x, y) => {
    setWidgets(
      widgets.map((w) => (w.id === id ? { ...w, x, y } : w))
    )
  }

  return (
    <div className="dashboard">
      <Navbar />
      <div className="dashboard-container" ref={containerRef}>
        {widgets.map((widget) => (
          <WidgetContainer
            key={widget.id}
            widget={widget}
            onRemove={removeWidget}
            onMove={updateWidgetPosition}
          />
        ))}

        <div className="add-widget-btn" onClick={() => setShowAddMenu(!showAddMenu)}>
          +
        </div>

        {showAddMenu && (
          <div className="widget-menu">
            <button onClick={() => addWidget('clock')}>Clock</button>
            <button onClick={() => addWidget('weather')}>Weather</button>
            <button onClick={() => addWidget('calendar')}>Calendar</button>
            <button onClick={() => addWidget('note')}>Note</button>
          </div>
        )}
      </div>
    </div>
  )
}
