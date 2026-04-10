import { api } from './client'

/** Staff only: imports all *.xml from data/private_sample_data/ on the server. */
export async function importPrivateSampleXml(): Promise<Record<string, unknown>> {
  const response = await api.post('/import-private-sample-xml/')
  return response.data
}
