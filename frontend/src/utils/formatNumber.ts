/**
 * Format a number with comma separators for thousands
 * @param value - The number to format
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted string with commas
 */
export const formatNumber = (value: number | string | null | undefined, decimals: number = 2): string => {
  if (value === null || value === undefined || value === '') {
    return ''
  }
  
  const numValue = typeof value === 'string' ? parseFloat(value) : value
  
  if (isNaN(numValue)) {
    return ''
  }
  
  // Format with commas and specified decimal places
  return numValue.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })
}

/**
 * Format a number with comma separators, but allow variable decimal places
 * @param value - The number to format
 * @param minDecimals - Minimum decimal places (default: 0)
 * @param maxDecimals - Maximum decimal places (default: 2)
 * @returns Formatted string with commas
 */
export const formatNumberFlexible = (value: number | string | null | undefined, minDecimals: number = 0, maxDecimals: number = 2): string => {
  if (value === null || value === undefined || value === '') {
    return ''
  }
  
  const numValue = typeof value === 'string' ? parseFloat(value) : value
  
  if (isNaN(numValue)) {
    return ''
  }
  
  // Format with commas and variable decimal places
  return numValue.toLocaleString('en-US', {
    minimumFractionDigits: minDecimals,
    maximumFractionDigits: maxDecimals
  })
}

/**
 * Format currency with comma separators
 * @param value - The number to format
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted string with $ and commas
 */
export const formatCurrency = (value: number | string | null | undefined, decimals: number = 2): string => {
  const formatted = formatNumber(value, decimals)
  return formatted ? `$${formatted}` : ''
}
