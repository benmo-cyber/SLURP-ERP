import { api } from './client'

export const getCalendarEvents = async (params?: {
  start_date?: string
  end_date?: string
  event_types?: string
}) => {
  const response = await api.get('/calendar/events/', { params })
  return response.data
}
