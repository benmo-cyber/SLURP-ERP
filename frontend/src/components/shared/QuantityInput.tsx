import { useState, useEffect } from 'react'
import './QuantityInput.css'

interface QuantityInputProps {
  value: number | string
  onChange: (value: number, unit: string) => void
  itemUnit?: string
  disabled?: boolean
  required?: boolean
  min?: number
  step?: number
  className?: string
}

function QuantityInput({ 
  value, 
  onChange, 
  itemUnit, 
  disabled = false, 
  required = false,
  min = 0,
  step = 0.01,
  className = ''
}: QuantityInputProps) {
  const [displayValue, setDisplayValue] = useState<string>(String(value || ''))
  const [displayUnit, setDisplayUnit] = useState<string>(itemUnit === 'kg' ? 'kg' : 'lbs')
  const [storedValue, setStoredValue] = useState<number>(typeof value === 'number' ? value : parseFloat(value) || 0)

  // Update display value when prop value changes
  useEffect(() => {
    if (value !== storedValue) {
      const numValue = typeof value === 'number' ? value : parseFloat(value) || 0
      setStoredValue(numValue)
      setDisplayValue(String(numValue))
    }
  }, [value, storedValue])

  // Initialize display unit from item unit
  useEffect(() => {
    if (itemUnit && (itemUnit === 'lbs' || itemUnit === 'kg')) {
      setDisplayUnit(itemUnit)
    }
  }, [itemUnit])

  const handleValueChange = (newValue: string) => {
    setDisplayValue(newValue)
    const numValue = parseFloat(newValue) || 0
    
    // Convert to item's unit if needed
    let convertedValue = numValue
    if (itemUnit && displayUnit !== itemUnit) {
      if (displayUnit === 'lbs' && itemUnit === 'kg') {
        convertedValue = numValue / 2.20462
      } else if (displayUnit === 'kg' && itemUnit === 'lbs') {
        convertedValue = numValue * 2.20462
      }
    }
    
    setStoredValue(convertedValue)
    onChange(convertedValue, itemUnit || displayUnit)
  }

  const handleUnitToggle = (newUnit: 'lbs' | 'kg') => {
    if (newUnit === displayUnit) return
    
    const currentValue = parseFloat(displayValue) || 0
    let convertedValue = currentValue
    
    // Convert value
    if (newUnit === 'lbs' && displayUnit === 'kg') {
      convertedValue = currentValue * 2.20462
    } else if (newUnit === 'kg' && displayUnit === 'lbs') {
      convertedValue = currentValue / 2.20462
    }
    
    setDisplayUnit(newUnit)
    setDisplayValue(convertedValue.toFixed(2))
    
    // Convert to item's unit if needed
    let finalValue = convertedValue
    if (itemUnit && newUnit !== itemUnit) {
      if (newUnit === 'lbs' && itemUnit === 'kg') {
        finalValue = convertedValue / 2.20462
      } else if (newUnit === 'kg' && itemUnit === 'lbs') {
        finalValue = convertedValue * 2.20462
      }
    }
    
    setStoredValue(finalValue)
    onChange(finalValue, itemUnit || newUnit)
  }

  const showToggle = itemUnit && (itemUnit === 'lbs' || itemUnit === 'kg')

  return (
    <div className={`quantity-input-wrapper ${className}`}>
      <input
        type="number"
        value={displayValue}
        onChange={(e) => handleValueChange(e.target.value)}
        disabled={disabled}
        required={required}
        min={min}
        step={step}
        className="quantity-input"
      />
      {showToggle && (
        <div className="unit-toggle-group">
          <button
            type="button"
            className={`unit-toggle-btn ${displayUnit === 'lbs' ? 'active' : ''}`}
            onClick={() => handleUnitToggle('lbs')}
            disabled={disabled}
          >
            lbs
          </button>
          <button
            type="button"
            className={`unit-toggle-btn ${displayUnit === 'kg' ? 'active' : ''}`}
            onClick={() => handleUnitToggle('kg')}
            disabled={disabled}
          >
            kg
          </button>
        </div>
      )}
    </div>
  )
}

export default QuantityInput


