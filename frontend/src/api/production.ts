import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const createFinishedProductSpecification = async (data: any) => {
  const response = await api.post('/finished-product-specifications/', data)
  return response.data
}

export const getFinishedProductSpecification = async (itemId: number) => {
  try {
    const response = await api.get(`/finished-product-specifications/?item=${itemId}`)
    const data = response.data.results || response.data
    const fps = Array.isArray(data) && data.length > 0 ? data[0] : null
    if (fps) {
      console.log(`FPS found for item ${itemId}:`, fps)
    } else {
      console.log(`No FPS found for item ${itemId}`)
    }
    return fps
  } catch (error: any) {
    console.error(`Error fetching FPS for item ${itemId}:`, error.response?.data || error.message)
    // FPS doesn't exist for this item
    return null
  }
}

export const getFpsPdfUrl = (fpsId: number) => {
  return `${API_BASE_URL}/finished-product-specifications/${fpsId}/generate_pdf/`
}
