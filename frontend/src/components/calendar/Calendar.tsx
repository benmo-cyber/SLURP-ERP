import { useState, useEffect } from 'react'
import { getCalendarEvents } from '../../api/calendar'
import { updateProductionBatch } from '../../api/inventory'
import './Calendar.css'

const DRAG_TYPE_BATCH = 'application/x-production-batch'

interface CalendarEvent {
  id: string
  type: 'shipment' | 'raw_material' | 'production' | 'receivable' | 'payable'
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
  ar_id?: number
  ap_id?: number
  balance?: number
  vendor_name?: string
  invoice_id?: number
  purchase_order_id?: number
  is_overdue?: boolean
  quantity_produced?: number
}

function Calendar() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [currentDate, setCurrentDate] = useState(new Date())
  const [viewMode, setViewMode] = useState<'month' | 'week' | 'day'>('month')
  const [selectedEventTypes, setSelectedEventTypes] = useState<string[]>(['shipments', 'raw_materials', 'production', 'receivables', 'payables'])
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)
  const [selectedDate, setSelectedDate] = useState<Date | null>(null)

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
      case 'receivable':
        return '#9b59b6' // Purple
      case 'payable':
        return '#e74c3c' // Red
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
      case 'receivable':
        return 'Receivable (AR)'
      case 'payable':
        return 'Payable (AP)'
      default:
        return type
    }
  }

  const getEventsForSelectedDate = (): CalendarEvent[] => {
    if (!selectedDate) return []
    const dateStr = selectedDate.toISOString().split('T')[0]
    const dayEvents = events.filter(event => event.date === dateStr)
    
    // Sort by event type: shipment, raw_material, production
    const typeOrder = { 'shipment': 0, 'raw_material': 1, 'production': 2 }
    return dayEvents.sort((a, b) => {
      const orderA = typeOrder[a.type as keyof typeof typeOrder] ?? 999
      const orderB = typeOrder[b.type as keyof typeof typeOrder] ?? 999
      return orderA - orderB
    })
  }

  const handleDateClick = (date: Date) => {
    setSelectedDate(date)
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

  const handleDragOver = (e: React.DragEvent) => {
    if (e.dataTransfer.types.includes(DRAG_TYPE_BATCH)) {
      e.preventDefault()
      e.dataTransfer.dropEffect = 'move'
    }
  }

  const handleDrop = async (e: React.DragEvent, dateStr: string) => {
    e.preventDefault()
    e.stopPropagation()
    const batchIdStr = e.dataTransfer.getData(DRAG_TYPE_BATCH)
    if (!batchIdStr || !dateStr) return
    const batchId = parseInt(batchIdStr, 10)
    if (Number.isNaN(batchId)) return
    try {
      await updateProductionBatch(batchId, { production_date: dateStr })
      await loadEvents()
    } catch (err) {
      console.error('Failed to move batch:', err)
      alert('Failed to move batch to this date')
    }
  }

  const handleProductionDragStart = (e: React.DragEvent, event: CalendarEvent) => {
    if (event.type !== 'production' || event.batch_id == null) return
    e.dataTransfer.setData(DRAG_TYPE_BATCH, String(event.batch_id))
    e.dataTransfer.effectAllowed = 'move'
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

              const dayDateStr = day.toISOString().split('T')[0]
              return (
                <div
                  key={dayIndex}
                  className={`calendar-day ${!isCurrentMonth ? 'other-month' : ''} ${isToday ? 'today' : ''} ${dayEvents.length > 0 ? 'has-events' : ''}`}
                  onClick={() => handleDateClick(day)}
                  data-date={dayDateStr}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, dayDateStr)}
                >
                  <div className="day-number">{day.getDate()}</div>
                  <div className="day-events" onClick={(e) => e.stopPropagation()}>
                    {dayEvents.slice(0, 3).map(event => (
                      <div
                        key={event.id}
                        className={`calendar-event ${event.type === 'production' ? 'draggable' : ''}`}
                        style={{ backgroundColor: getEventTypeColor(event.type) }}
                        onClick={() => setSelectedEvent(event)}
                        title={event.title}
                        draggable={event.type === 'production'}
                        onDragStart={(e) => handleProductionDragStart(e, event)}
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

            const dayDateStr = day.toISOString().split('T')[0]
            return (
              <div 
                key={index} 
                className={`week-day-column ${isToday ? 'today' : ''} ${dayEvents.length > 0 ? 'has-events' : ''}`}
                onClick={() => handleDateClick(day)}
                data-date={dayDateStr}
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, dayDateStr)}
              >
                <div className="week-day-header">
                  <div className="week-day-name">
                    {day.toLocaleDateString('en-US', { weekday: 'short' })}
                  </div>
                  <div className="week-day-number">{day.getDate()}</div>
                </div>
                <div className="week-day-events" onClick={(e) => e.stopPropagation()}>
                  {dayEvents.map(event => (
                    <div
                      key={event.id}
                      className={`week-event ${event.type === 'production' ? 'draggable' : ''}`}
                      style={{ borderLeftColor: getEventTypeColor(event.type) }}
                      onClick={() => setSelectedEvent(event)}
                      draggable={event.type === 'production'}
                      onDragStart={(e) => handleProductionDragStart(e, event)}
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
    const dayDateStr = currentDate.toISOString().split('T')[0]

    return (
      <div className="calendar-day-view">
        <div className={`day-header ${isToday ? 'today' : ''}`}>
          <h3>{currentDate.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</h3>
        </div>
        <div
          className="day-events-list"
          data-date={dayDateStr}
          onDragOver={handleDragOver}
          onDrop={(e) => handleDrop(e, dayDateStr)}
        >
          {dayEvents.length === 0 ? (
            <div className="no-events">No events scheduled for this day</div>
          ) : (
            dayEvents.map(event => (
              <div
                key={event.id}
                className={`day-event-card ${event.type === 'production' ? 'draggable' : ''}`}
                style={{ borderLeftColor: getEventTypeColor(event.type) }}
                onClick={() => setSelectedEvent(event)}
                draggable={event.type === 'production'}
                onDragStart={(e) => handleProductionDragStart(e, event)}
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
        <button
          className={selectedEventTypes.includes('receivables') ? 'active' : ''}
          onClick={() => toggleEventType('receivables')}
        >
          Receivables (AR)
        </button>
        <button
          className={selectedEventTypes.includes('payables') ? 'active' : ''}
          onClick={() => toggleEventType('payables')}
        >
          Payables (AP)
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

      {selectedDate && (
        <div className="modal-overlay" onClick={() => setSelectedDate(null)}>
          <div className="date-events-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Events for {selectedDate.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</h3>
              <button className="close-button" onClick={() => setSelectedDate(null)}>×</button>
            </div>
            <div className="date-events-content">
              {getEventsForSelectedDate().length === 0 ? (
                <div className="no-events">No events scheduled for this day</div>
              ) : (
                <div className="events-by-type">
                  {['shipment', 'raw_material', 'production', 'receivable', 'payable'].map(type => {
                    const typeEvents = getEventsForSelectedDate().filter(e => e.type === type)
                    if (typeEvents.length === 0) return null
                    
                    return (
                      <div key={type} className="event-type-group">
                        <div className="event-type-header" style={{ backgroundColor: getEventTypeColor(type) }}>
                          <h4>{getEventTypeLabel(type)} ({typeEvents.length})</h4>
                        </div>
                        <div className="event-type-list">
                          {typeEvents.map(event => (
                            <div
                              key={event.id}
                              className="date-event-item"
                              onClick={() => {
                                setSelectedDate(null)
                                setSelectedEvent(event)
                              }}
                            >
                              <div className="event-item-title">{event.title}</div>
                              <div className="event-item-details">
                                {event.sales_order_number && (
                                  <span>SO: {event.sales_order_number}</span>
                                )}
                                {event.customer_name && (
                                  <span>Customer: {event.customer_name}</span>
                                )}
                                {event.lot_number && (
                                  <span>Lot: {event.lot_number}</span>
                                )}
                                {event.item_name && (
                                  <span>Item: {event.item_name}</span>
                                )}
                                {event.po_number && (
                                  <span>PO: {event.po_number}</span>
                                )}
                                {event.batch_number && (
                                  <span>Batch: {event.batch_number}</span>
                                )}
                                {event.status && (
                                  <span className="status-badge">{event.status}</span>
                                )}
                                {event.is_scheduled && (
                                  <span className="scheduled-badge">Scheduled</span>
                                )}
                                {event.is_actual && (
                                  <span className="actual-badge">Actual</span>
                                )}
                                {event.balance != null && (
                                  <span>Balance: ${event.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                                )}
                                {event.vendor_name && (
                                  <span>Vendor: {event.vendor_name}</span>
                                )}
                                {event.is_overdue && (
                                  <span className="overdue-badge">Overdue</span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
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
                <strong>Type</strong>
                <span className="event-type-badge" style={{ backgroundColor: getEventTypeColor(selectedEvent.type) }}>
                  {getEventTypeLabel(selectedEvent.type)}
                </span>
              </div>
              <div className="detail-row">
                <strong>Title</strong>
                <span>{selectedEvent.title}</span>
              </div>
              <div className="detail-row">
                <strong>Date</strong>
                <span>{new Date(selectedEvent.date).toLocaleDateString()}</span>
              </div>
              {selectedEvent.type === 'production' && (
                <>
                  {selectedEvent.batch_number != null && (
                    <div className="detail-row">
                      <strong>Batch number</strong>
                      <span>{selectedEvent.batch_number}</span>
                    </div>
                  )}
                  {selectedEvent.status != null && (
                    <div className="detail-row">
                      <strong>Status</strong>
                      <span>{selectedEvent.status}</span>
                    </div>
                  )}
                  {selectedEvent.quantity_produced != null && (
                    <div className="detail-row">
                      <strong>Quantity produced</strong>
                      <span>{Number(selectedEvent.quantity_produced).toLocaleString()}</span>
                    </div>
                  )}
                </>
              )}
              {selectedEvent.type === 'shipment' && (
                <>
                  {selectedEvent.sales_order_number != null && (
                    <div className="detail-row">
                      <strong>Sales order</strong>
                      <span>{selectedEvent.sales_order_number}</span>
                    </div>
                  )}
                  {selectedEvent.customer_name != null && (
                    <div className="detail-row">
                      <strong>Customer</strong>
                      <span>{selectedEvent.customer_name}</span>
                    </div>
                  )}
                  {selectedEvent.status != null && (
                    <div className="detail-row">
                      <strong>Status</strong>
                      <span>{selectedEvent.status}</span>
                    </div>
                  )}
                </>
              )}
              {selectedEvent.type === 'raw_material' && (
                <>
                  {selectedEvent.lot_number != null && (
                    <div className="detail-row">
                      <strong>Lot number</strong>
                      <span>{selectedEvent.lot_number}</span>
                    </div>
                  )}
                  {selectedEvent.item_name != null && (
                    <div className="detail-row">
                      <strong>Item</strong>
                      <span>{selectedEvent.item_name}</span>
                    </div>
                  )}
                  {selectedEvent.po_number != null && (
                    <div className="detail-row">
                      <strong>PO number</strong>
                      <span>{selectedEvent.po_number}</span>
                    </div>
                  )}
                </>
              )}
              {selectedEvent.type === 'receivable' && (
                <>
                  {selectedEvent.customer_name != null && (
                    <div className="detail-row">
                      <strong>Customer</strong>
                      <span>{selectedEvent.customer_name}</span>
                    </div>
                  )}
                  {selectedEvent.balance != null && (
                    <div className="detail-row">
                      <strong>Balance</strong>
                      <span>${selectedEvent.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                    </div>
                  )}
                  {selectedEvent.is_overdue && (
                    <div className="detail-row">
                      <strong></strong>
                      <span className="overdue-badge">Overdue</span>
                    </div>
                  )}
                </>
              )}
              {selectedEvent.type === 'payable' && (
                <>
                  {selectedEvent.vendor_name != null && (
                    <div className="detail-row">
                      <strong>Vendor</strong>
                      <span>{selectedEvent.vendor_name}</span>
                    </div>
                  )}
                  {selectedEvent.balance != null && (
                    <div className="detail-row">
                      <strong>Balance</strong>
                      <span>${selectedEvent.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                    </div>
                  )}
                  {selectedEvent.is_overdue && (
                    <div className="detail-row">
                      <strong></strong>
                      <span className="overdue-badge">Overdue</span>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Calendar
