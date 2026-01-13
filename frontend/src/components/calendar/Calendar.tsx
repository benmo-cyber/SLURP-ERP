import { useState, useEffect } from 'react'
import { getCalendarEvents } from '../../api/calendar'
import './Calendar.css'

interface CalendarEvent {
  id: string
  type: 'shipment' | 'raw_material' | 'production'
  title: string
  date: string
  sales_order_id?: number
  sales_order_number?: string
  customer_name?: string
  is_actual?: boolean
  lot_id?: number
  lot_number?: string
  item_name?: string
  po_number?: string
  batch_id?: number
  batch_number?: string
  status?: string
  is_scheduled?: boolean
}

function Calendar() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [currentDate, setCurrentDate] = useState(new Date())
  const [viewMode, setViewMode] = useState<'month' | 'week' | 'day'>('month')
  const [selectedEventTypes, setSelectedEventTypes] = useState<string[]>(['shipments', 'raw_materials', 'production'])
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)

  useEffect(() => {
    loadEvents()
  }, [currentDate, viewMode, selectedEventTypes])

  const loadEvents = async () => {
    try {
      setLoading(true)
      const startDate = getStartDate()
      const endDate = getEndDate()
      
      const params: any = {
        start_date: startDate.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
        event_types: selectedEventTypes.join(',')
      }
      
      const data = await getCalendarEvents(params)
      setEvents(data.events || [])
    } catch (error) {
      console.error('Failed to load calendar events:', error)
      alert('Failed to load calendar events')
    } finally {
      setLoading(false)
    }
  }

  const getStartDate = (): Date => {
    const date = new Date(currentDate)
    if (viewMode === 'month') {
      date.setDate(1)
      date.setDate(date.getDate() - date.getDay()) // Start of week
    } else if (viewMode === 'week') {
      const day = date.getDay()
      date.setDate(date.getDate() - day)
    }
    return date
  }

  const getEndDate = (): Date => {
    const date = new Date(currentDate)
    if (viewMode === 'month') {
      date.setMonth(date.getMonth() + 1)
      date.setDate(0) // Last day of current month
      const day = date.getDay()
      date.setDate(date.getDate() + (6 - day)) // End of week
    } else if (viewMode === 'week') {
      const day = date.getDay()
      date.setDate(date.getDate() + (6 - day))
    } else {
      // Day view
    }
    return date
  }

  const getEventsForDate = (date: Date): CalendarEvent[] => {
    const dateStr = date.toISOString().split('T')[0]
    return events.filter(event => event.date === dateStr)
  }

  const getEventTypeColor = (type: string): string => {
    switch (type) {
      case 'shipment':
        return '#3498db' // Blue
      case 'raw_material':
        return '#27ae60' // Green
      case 'production':
        return '#f39c12' // Orange
      default:
        return '#95a5a6'
    }
  }

  const getEventTypeLabel = (type: string): string => {
    switch (type) {
      case 'shipment':
        return 'Shipment'
      case 'raw_material':
        return 'Raw Material'
      case 'production':
        return 'Production'
      default:
        return type
    }
  }

  const navigateDate = (direction: 'prev' | 'next') => {
    const newDate = new Date(currentDate)
    if (viewMode === 'month') {
      newDate.setMonth(newDate.getMonth() + (direction === 'next' ? 1 : -1))
    } else if (viewMode === 'week') {
      newDate.setDate(newDate.getDate() + (direction === 'next' ? 7 : -7))
    } else {
      newDate.setDate(newDate.getDate() + (direction === 'next' ? 1 : -1))
    }
    setCurrentDate(newDate)
  }

  const goToToday = () => {
    setCurrentDate(new Date())
  }

  const toggleEventType = (type: string) => {
    setSelectedEventTypes(prev => {
      if (prev.includes(type)) {
        return prev.filter(t => t !== type)
      } else {
        return [...prev, type]
      }
    })
  }

  const renderMonthView = () => {
    const startDate = getStartDate()
    const endDate = getEndDate()
    const days: Date[] = []
    const current = new Date(startDate)

    while (current <= endDate) {
      days.push(new Date(current))
      current.setDate(current.getDate() + 1)
    }

    const weeks: Date[][] = []
    for (let i = 0; i < days.length; i += 7) {
      weeks.push(days.slice(i, i + 7))
    }

    return (
      <div className="calendar-month">
        <div className="calendar-weekdays">
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
            <div key={day} className="weekday-header">{day}</div>
          ))}
        </div>
        {weeks.map((week, weekIndex) => (
          <div key={weekIndex} className="calendar-week">
            {week.map((day, dayIndex) => {
              const dayEvents = getEventsForDate(day)
              const isToday = day.toDateString() === new Date().toDateString()
              const isCurrentMonth = day.getMonth() === currentDate.getMonth()

              return (
                <div
                  key={dayIndex}
                  className={`calendar-day ${!isCurrentMonth ? 'other-month' : ''} ${isToday ? 'today' : ''}`}
                >
                  <div className="day-number">{day.getDate()}</div>
                  <div className="day-events">
                    {dayEvents.slice(0, 3).map(event => (
                      <div
                        key={event.id}
                        className="calendar-event"
                        style={{ backgroundColor: getEventTypeColor(event.type) }}
                        onClick={() => setSelectedEvent(event)}
                        title={event.title}
                      >
                        {event.title}
                      </div>
                    ))}
                    {dayEvents.length > 3 && (
                      <div className="more-events">+{dayEvents.length - 3} more</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    )
  }

  const renderWeekView = () => {
    const startDate = getStartDate()
    const days: Date[] = []
    const current = new Date(startDate)

    for (let i = 0; i < 7; i++) {
      days.push(new Date(current))
      current.setDate(current.getDate() + 1)
    }

    return (
      <div className="calendar-week-view">
        <div className="week-header">
          {days.map((day, index) => {
            const dayEvents = getEventsForDate(day)
            const isToday = day.toDateString() === new Date().toDateString()

            return (
              <div key={index} className={`week-day-column ${isToday ? 'today' : ''}`}>
                <div className="week-day-header">
                  <div className="week-day-name">
                    {day.toLocaleDateString('en-US', { weekday: 'short' })}
                  </div>
                  <div className="week-day-number">{day.getDate()}</div>
                </div>
                <div className="week-day-events">
                  {dayEvents.map(event => (
                    <div
                      key={event.id}
                      className="week-event"
                      style={{ borderLeftColor: getEventTypeColor(event.type) }}
                      onClick={() => setSelectedEvent(event)}
                    >
                      <div className="event-time">{event.type}</div>
                      <div className="event-title">{event.title}</div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  const renderDayView = () => {
    const dayEvents = getEventsForDate(currentDate)
    const isToday = currentDate.toDateString() === new Date().toDateString()

    return (
      <div className="calendar-day-view">
        <div className={`day-header ${isToday ? 'today' : ''}`}>
          <h3>{currentDate.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</h3>
        </div>
        <div className="day-events-list">
          {dayEvents.length === 0 ? (
            <div className="no-events">No events scheduled for this day</div>
          ) : (
            dayEvents.map(event => (
              <div
                key={event.id}
                className="day-event-card"
                style={{ borderLeftColor: getEventTypeColor(event.type) }}
                onClick={() => setSelectedEvent(event)}
              >
                <div className="event-type-badge" style={{ backgroundColor: getEventTypeColor(event.type) }}>
                  {getEventTypeLabel(event.type)}
                </div>
                <div className="event-details">
                  <h4>{event.title}</h4>
                  {event.sales_order_number && (
                    <p>Sales Order: {event.sales_order_number}</p>
                  )}
                  {event.customer_name && (
                    <p>Customer: {event.customer_name}</p>
                  )}
                  {event.lot_number && (
                    <p>Lot: {event.lot_number}</p>
                  )}
                  {event.batch_number && (
                    <p>Batch: {event.batch_number}</p>
                  )}
                  {event.is_scheduled && (
                    <span className="scheduled-badge">Scheduled</span>
                  )}
                  {event.is_actual && (
                    <span className="actual-badge">Actual</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="calendar-page">
      <div className="calendar-header">
        <h2>Calendar</h2>
        <div className="calendar-controls">
          <div className="view-mode-toggle">
            <button
              className={viewMode === 'month' ? 'active' : ''}
              onClick={() => setViewMode('month')}
            >
              Month
            </button>
            <button
              className={viewMode === 'week' ? 'active' : ''}
              onClick={() => setViewMode('week')}
            >
              Week
            </button>
            <button
              className={viewMode === 'day' ? 'active' : ''}
              onClick={() => setViewMode('day')}
            >
              Day
            </button>
          </div>
          <div className="date-navigation">
            <button onClick={() => navigateDate('prev')}>‹</button>
            <button onClick={goToToday}>Today</button>
            <span className="current-date">
              {viewMode === 'month' && currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
              {viewMode === 'week' && `${getStartDate().toLocaleDateString()} - ${getEndDate().toLocaleDateString()}`}
              {viewMode === 'day' && currentDate.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            </span>
            <button onClick={() => navigateDate('next')}>›</button>
          </div>
        </div>
      </div>

      <div className="calendar-filters">
        <label>Event Types:</label>
        <button
          className={selectedEventTypes.includes('shipments') ? 'active' : ''}
          onClick={() => toggleEventType('shipments')}
        >
          Shipments
        </button>
        <button
          className={selectedEventTypes.includes('raw_materials') ? 'active' : ''}
          onClick={() => toggleEventType('raw_materials')}
        >
          Raw Materials
        </button>
        <button
          className={selectedEventTypes.includes('production') ? 'active' : ''}
          onClick={() => toggleEventType('production')}
        >
          Production
        </button>
      </div>

      {loading ? (
        <div className="loading">Loading calendar events...</div>
      ) : (
        <div className="calendar-content">
          {viewMode === 'month' && renderMonthView()}
          {viewMode === 'week' && renderWeekView()}
          {viewMode === 'day' && renderDayView()}
        </div>
      )}

      {selectedEvent && (
        <div className="modal-overlay" onClick={() => setSelectedEvent(null)}>
          <div className="event-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Event Details</h3>
              <button className="close-button" onClick={() => setSelectedEvent(null)}>×</button>
            </div>
            <div className="event-detail-content">
              <div className="detail-row">
                <strong>Type:</strong>
                <span className="event-type-badge" style={{ backgroundColor: getEventTypeColor(selectedEvent.type) }}>
                  {getEventTypeLabel(selectedEvent.type)}
                </span>
              </div>
              <div className="detail-row">
                <strong>Title:</strong>
                <span>{selectedEvent.title}</span>
              </div>
              <div className="detail-row">
                <strong>Date:</strong>
                <span>{new Date(selectedEvent.date).toLocaleDateString()}</span>
              </div>
              {selectedEvent.sales_order_number && (
                <div className="detail-row">
                  <strong>Sales Order:</strong>
                  <span>{selectedEvent.sales_order_number}</span>
                </div>
              )}
              {selectedEvent.customer_name && (
                <div className="detail-row">
                  <strong>Customer:</strong>
                  <span>{selectedEvent.customer_name}</span>
                </div>
              )}
              {selectedEvent.lot_number && (
                <div className="detail-row">
                  <strong>Lot Number:</strong>
                  <span>{selectedEvent.lot_number}</span>
                </div>
              )}
              {selectedEvent.item_name && (
                <div className="detail-row">
                  <strong>Item:</strong>
                  <span>{selectedEvent.item_name}</span>
                </div>
              )}
              {selectedEvent.po_number && (
                <div className="detail-row">
                  <strong>PO Number:</strong>
                  <span>{selectedEvent.po_number}</span>
                </div>
              )}
              {selectedEvent.batch_number && (
                <div className="detail-row">
                  <strong>Batch Number:</strong>
                  <span>{selectedEvent.batch_number}</span>
                </div>
              )}
              {selectedEvent.status && (
                <div className="detail-row">
                  <strong>Status:</strong>
                  <span>{selectedEvent.status}</span>
                </div>
              )}
              {selectedEvent.is_scheduled && (
                <div className="detail-row">
                  <strong>Type:</strong>
                  <span className="scheduled-badge">Scheduled</span>
                </div>
              )}
              {selectedEvent.is_actual && (
                <div className="detail-row">
                  <strong>Type:</strong>
                  <span className="actual-badge">Actual</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Calendar
