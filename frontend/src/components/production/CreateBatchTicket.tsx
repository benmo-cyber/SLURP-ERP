import { useState, useEffect } from 'react'
import { getItems, getFormulas, getLots, createProductionBatch, getItemPackSizes, getPartialLots } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import { useBackdatedEntry } from '../../context/BackdatedEntryContext'
import './CreateBatchTicket.css'

interface Item {
  id: number
  sku: string
  name: string
  unit_of_measure: string
  item_type: string
}

interface Formula {
  id: number
  finished_good: Item
  version: string
  ingredients: FormulaItem[]
}

interface FormulaItem {
  id: number
  item: Item
  percentage: number
}

interface Lot {
  id: number
  lot_number: string
  vendor_lot_number?: string | null
  item: Item
  quantity_remaining: number
  status: string
}

interface CreateBatchTicketProps {
  onClose: () => void
  onSuccess: () => void
}

function CreateBatchTicket({ onClose, onSuccess }: CreateBatchTicketProps) {
  const { minDateForEntry } = useBackdatedEntry()
  const [batchType, setBatchType] = useState<'production' | 'repack'>('production')
  const [finishedGoods, setFinishedGoods] = useState<Item[]>([])
  const [repackItems, setRepackItems] = useState<Item[]>([])
  const [formulas, setFormulas] = useState<Formula[]>([])
  const [allLots, setAllLots] = useState<Lot[]>([])
  const [availableLots, setAvailableLots] = useState<Lot[]>([])
  const [selectedFinishedGood, setSelectedFinishedGood] = useState<Item | null>(null)
  const [selectedRepackItem, setSelectedRepackItem] = useState<Item | null>(null)
  const [selectedFormula, setSelectedFormula] = useState<Formula | null>(null)
  const [quantity, setQuantity] = useState('')
  const [quantityUnit, setQuantityUnit] = useState<'lbs' | 'kg'>('lbs')
  const [selectedLots, setSelectedLots] = useState<{ [key: number]: number }>({})
  const [lotInputValues, setLotInputValues] = useState<{ [key: number]: string }>({})
  const [productionDate, setProductionDate] = useState<string>(new Date().toISOString().split('T')[0])
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)
  const [outputPackSizeId, setOutputPackSizeId] = useState<string>('')
  const [availableOutputPackSizes, setAvailableOutputPackSizes] = useState<any[]>([])
  const [indirectMaterialLots, setIndirectMaterialLots] = useState<Lot[]>([])
  const [selectedIndirectMaterials, setSelectedIndirectMaterials] = useState<{ [key: number]: number }>({})
  const [indirectMaterialInputValues, setIndirectMaterialInputValues] = useState<{ [key: number]: string }>({})
  const [partialLots, setPartialLots] = useState<Lot[]>([])
  const [selectedPartials, setSelectedPartials] = useState<Set<number>>(new Set())
  /** Per-formula-ingredient override: use formula item (default) or substitute with another raw material */
  const [ingredientOverrides, setIngredientOverrides] = useState<Record<number, { useFormula: boolean; substituteItemId: number | null }>>({})
  /** Per-ingredient percentage override for this batch (e.g. 75% instead of 50% when material has degraded) */
  const [ingredientPercentageOverrides, setIngredientPercentageOverrides] = useState<Record<number, number | null>>({})

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (batchType === 'production' && selectedFinishedGood) {
      console.log('Finding formula for finished good:', selectedFinishedGood)
      console.log('Available formulas:', formulas.map(f => ({ id: f.id, finishedGoodId: f.finished_good?.id, finishedGoodSku: f.finished_good?.sku })))
      const formula = formulas.find(f => f.finished_good.id === selectedFinishedGood.id)
      console.log('Found formula:', formula)
      if (formula) {
        console.log('Formula ingredients:', formula.ingredients)
        console.log('Formula ingredients count:', formula.ingredients?.length || 0)
        if (!formula.ingredients || formula.ingredients.length === 0) {
          alert(`Warning: Formula for ${selectedFinishedGood.sku} has no ingredients. Please add ingredients to the formula.`)
        } else {
          console.log('Ingredient SKUs:', formula.ingredients.map(ing => ing.item?.sku))
        }
      } else {
        alert(`No formula found for ${selectedFinishedGood.sku}. Please create a formula first.`)
      }
      setSelectedFormula(formula || null)
      setIngredientOverrides({})
      setIngredientPercentageOverrides({})
      
      // Load partial lots for this finished good
      loadPartialLots(selectedFinishedGood.id)
    } else {
      setSelectedFormula(null)
      setPartialLots([])
      setSelectedPartials(new Set())
    }
    
    if (batchType === 'repack') {
      setSelectedLots({})
      setLotInputValues({})
      if (selectedRepackItem) {
        // Filter lots for the selected repack item
        const itemLots = allLots.filter((lot: Lot) => lot.item.id === selectedRepackItem.id)
        setAvailableLots(itemLots)
      } else {
        setAvailableLots([])
      }
    }
  }, [batchType, selectedFinishedGood, selectedRepackItem, formulas, allLots])

  useEffect(() => {
    console.log('useEffect triggered for loadAvailableLots:', {
      batchType,
      hasSelectedFormula: !!selectedFormula,
      allLotsCount: allLots.length,
      selectedFormula: selectedFormula
    })
    if (batchType === 'production' && selectedFormula && allLots.length > 0) {
      console.log('Calling loadAvailableLots with formula:', selectedFormula)
      loadAvailableLots(selectedFormula)
    } else if (batchType === 'production' && selectedFormula && allLots.length === 0) {
      console.warn('Selected formula but no lots available')
      setAvailableLots([])
    } else if (batchType === 'production' && !selectedFormula) {
      console.warn('Production mode but no formula selected')
      setAvailableLots([])
    }
  }, [batchType, selectedFormula, allLots])


  const loadPartialLots = async (finishedGoodItemId: number) => {
    try {
      const partials = await getPartialLots(finishedGoodItemId)
      setPartialLots(partials)
      console.log('Loaded partial lots:', partials)
    } catch (error) {
      console.error('Failed to load partial lots:', error)
      setPartialLots([])
    }
  }

  const handlePartialToggle = (lotId: number) => {
    const newSelected = new Set(selectedPartials)
    if (newSelected.has(lotId)) {
      newSelected.delete(lotId)
    } else {
      newSelected.add(lotId)
    }
    setSelectedPartials(newSelected)
  }

  const loadData = async () => {
    try {
      setLoading(true)
      const [itemsData, formulasData, lotsData] = await Promise.all([
        getItems(),
        getFormulas(),
        getLots()
      ])
      
      console.log('Loaded lots data:', lotsData)
      console.log('Total lots received:', lotsData.length)
      
      const finishedGoods = itemsData.filter((item: Item) => item.item_type === 'finished_good')
      const repackItems = itemsData.filter((item: Item) => 
        item.item_type === 'distributed_item' || item.item_type === 'raw_material'
      )
      setFinishedGoods(finishedGoods)
      setRepackItems(repackItems)
      
      // Load indirect material lots
      const indirectMaterialLots = lotsData.filter((lot: Lot) => 
        lot.item.item_type === 'indirect_material' && 
        lot.quantity_remaining > 0 &&
        (!lot.status || lot.status === 'accepted')
      )
      setIndirectMaterialLots(indirectMaterialLots)
      
      // Debug formulas
      console.log('Loaded formulas:', formulasData)
      formulasData.forEach((formula: Formula) => {
        console.log(`Formula ${formula.id} for ${formula.finished_good?.sku}:`, {
          finishedGood: formula.finished_good,
          ingredients: formula.ingredients,
          ingredientCount: formula.ingredients?.length || 0
        })
      })
      
      setFormulas(formulasData)
      
      // Filter to only show accepted lots with remaining quantity
      // If status is not set, assume it's accepted (for backward compatibility)
      const validLots = lotsData.filter((lot: Lot) => {
        const hasItem = lot.item && lot.item.sku
        // Status might be undefined/null for older lots, so treat as accepted if not set
        const isAccepted = !lot.status || lot.status === 'accepted'
        const hasQuantity = lot.quantity_remaining && lot.quantity_remaining > 0
        
        if (!hasItem) {
          console.warn('Lot missing item:', lot)
        }
        if (!isAccepted) {
          console.log('Lot not accepted:', lot.lot_number, 'status:', lot.status)
        }
        if (!hasQuantity) {
          console.log('Lot has no remaining quantity:', lot.lot_number, 'remaining:', lot.quantity_remaining)
        }
        
        return hasItem && isAccepted && hasQuantity
      })
      
      console.log('Filtered valid lots:', validLots.length, 'out of', lotsData.length)
      console.log('Valid lots:', validLots)
      setAllLots(validLots)
    } catch (error) {
      console.error('Failed to load data:', error)
      alert('Failed to load data. Please check the console for details.')
    } finally {
      setLoading(false)
    }
  }

  const loadAvailableLots = (formula: Formula | null) => {
    console.log('=== loadAvailableLots called ===', formula)
    if (!formula) {
      console.warn('loadAvailableLots: No formula provided')
      setAvailableLots([])
      return
    }

    // Check if formula has ingredients
    if (!formula.ingredients || formula.ingredients.length === 0) {
      console.warn('Formula has no ingredients:', formula)
      // If no ingredients, show all available lots as a fallback
      console.log('No ingredients found - showing all available lots as fallback')
      const fallbackLots = allLots.filter((lot: Lot) => {
        const isAccepted = !lot.status || lot.status === 'accepted'
        const hasQuantity = lot.quantity_remaining && lot.quantity_remaining > 0
        return isAccepted && hasQuantity
      })
      console.log('Fallback lots:', fallbackLots.length)
      setAvailableLots(fallbackLots)
      return
    }

    // Filter lots to only show those that match formula ingredients by SKU (not vendor-specific item.id)
    // This allows interchangeability of materials from different vendors
    const ingredientSkus = formula.ingredients
      .map(ing => ing.item?.sku)
      .filter(Boolean)
      .map(sku => sku?.trim().toUpperCase())
    
    if (ingredientSkus.length === 0) {
      console.warn('Formula ingredients have no SKUs:', formula.ingredients)
      setAvailableLots([])
      return
    }
    
    console.log('Filtering lots for formula:', {
      formulaId: formula.id,
      finishedGood: formula.finished_good?.sku,
      ingredientCount: formula.ingredients.length,
      ingredientSkus,
      ingredientDetails: formula.ingredients.map(ing => ({
        id: ing.id,
        itemId: ing.item?.id,
        itemSku: ing.item?.sku,
        itemName: ing.item?.name,
        percentage: ing.percentage
      })),
      totalLots: allLots.length,
      allLotSkus: allLots.map(l => l.item?.sku).filter(Boolean),
      allLotDetails: allLots.map(l => ({
        lotId: l.id,
        lotNumber: l.lot_number,
        itemId: l.item?.id,
        itemSku: l.item?.sku,
        itemName: l.item?.name,
        status: l.status,
        quantityRemaining: l.quantity_remaining
      }))
    })
    
    const filteredLots = allLots.filter((lot: Lot) => {
      const lotSku = lot.item?.sku?.trim().toUpperCase()
      const matchesSku = lotSku && ingredientSkus.includes(lotSku)
      // Status might be undefined/null for older lots, so treat as accepted if not set
      const isAccepted = !lot.status || lot.status === 'accepted'
      const hasQuantity = lot.quantity_remaining && lot.quantity_remaining > 0
      
      if (matchesSku && !isAccepted) {
        console.log('Lot matches SKU but not accepted:', lot.lot_number, lot.item.sku, 'status:', lot.status)
      }
      if (matchesSku && !hasQuantity) {
        console.log('Lot matches SKU but no quantity:', lot.lot_number, lot.item.sku, 'remaining:', lot.quantity_remaining)
      }
      if (!matchesSku && lot.item?.sku) {
        console.log('Lot SKU does not match ingredients:', lot.lot_number, 'lot SKU:', lot.item.sku, 'ingredient SKUs:', ingredientSkus)
      }
      
      return matchesSku && isAccepted && hasQuantity
    })
    
    console.log('Available lots for formula:', {
      ingredientSkus,
      totalLots: allLots.length,
      filteredLots: filteredLots.length,
      lots: filteredLots.map(l => ({ id: l.id, lot_number: l.lot_number, sku: l.item?.sku, qty: l.quantity_remaining }))
    })
    
    setAvailableLots(filteredLots)
  }

  const convertWeight = (value: number, from: 'lbs' | 'kg', to: 'lbs' | 'kg'): number => {
    if (from === to) return value
    if (from === 'lbs' && to === 'kg') {
      const converted = value / 2.20462
      // Round to 2 decimal places to avoid floating point precision issues
      return Math.round(converted * 100) / 100
    }
    if (from === 'kg' && to === 'lbs') {
      const converted = value * 2.20462
      // Round to 2 decimal places to avoid floating point precision issues
      return Math.round(converted * 100) / 100
    }
    return value
  }

  const handleLotQuantityChange = (lotId: number, quantity: string, lotUnitOfMeasure: string) => {
    // Update the input value state - preserve as string to avoid any parsing issues
    const newInputValues = { ...lotInputValues }
    if (quantity === '') {
      delete newInputValues[lotId]
    } else {
      newInputValues[lotId] = quantity
    }
    setLotInputValues(newInputValues)
    
    // Convert and store in lot's native unit
    const newSelectedLots = { ...selectedLots }
    if (quantity === '' || parseFloat(quantity) <= 0 || isNaN(parseFloat(quantity))) {
      delete newSelectedLots[lotId]
    } else {
      // User enters quantity in quantityUnit (display unit)
      // Convert to lot's native unit for storage
      // Parse carefully to preserve exact integers
      const parsedQuantity = parseFloat(quantity)
      
      // If units match, preserve exact value (no conversion needed)
      if (quantityUnit === lotUnitOfMeasure) {
        // Check if the string represents a whole number (no decimal point)
        const isIntegerString = !quantity.includes('.')
        if (isIntegerString) {
          // Store as exact integer - parse as integer to avoid any floating point issues
          newSelectedLots[lotId] = parseInt(quantity, 10)
        } else {
          // Has decimal - check if it's effectively a whole number (within floating point tolerance)
          const rounded = Math.round(parsedQuantity)
          const isWholeNumber = Math.abs(parsedQuantity - rounded) < 0.0000001
          if (isWholeNumber) {
            // Store as exact integer
            newSelectedLots[lotId] = rounded
          } else {
            // Round to 2 decimal places for decimals
            newSelectedLots[lotId] = Math.round(parsedQuantity * 100) / 100
          }
        }
      } else {
        // Need to convert from display unit (quantityUnit) to lot's native unit
        const quantityInLotUnit = convertWeight(parsedQuantity, quantityUnit, lotUnitOfMeasure as 'lbs' | 'kg')
        newSelectedLots[lotId] = quantityInLotUnit
      }
    }
    setSelectedLots(newSelectedLots)
  }
  
  const handleQuantityUnitChange = (newUnit: 'lbs' | 'kg') => {
    // When main unit changes, convert all lot input values and stored values
    const convertedInputValues: { [key: number]: string } = {}
    const convertedStoredValues: { [key: number]: number } = {}
    
    Object.keys(lotInputValues).forEach(lotIdStr => {
      const lotId = parseInt(lotIdStr)
      const lot = [...availableLots, ...allLots].find(l => l.id === lotId)
      if (lot && lotInputValues[lotId]) {
        const currentValue = parseFloat(lotInputValues[lotId])
        if (!isNaN(currentValue)) {
          // Convert input value from old unit to new unit
          const convertedInput = convertWeight(currentValue, quantityUnit, newUnit)
          convertedInputValues[lotId] = formatNumber(convertedInput)
          
          // Convert stored value: from old display unit to lot's native unit
          // First convert from old display unit to new display unit, then to lot's native unit
          let quantityInNewDisplayUnit = convertWeight(currentValue, quantityUnit, newUnit)
          let quantityInLotUnit = quantityInNewDisplayUnit
          if (newUnit !== lot.item.unit_of_measure) {
            quantityInLotUnit = convertWeight(quantityInNewDisplayUnit, newUnit, lot.item.unit_of_measure as 'lbs' | 'kg')
          }
          convertedStoredValues[lotId] = quantityInLotUnit
        }
      }
    })
    
    setLotInputValues(convertedInputValues)
    setSelectedLots(convertedStoredValues)
    setQuantityUnit(newUnit)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (batchType === 'production') {
      if (!selectedFinishedGood || !selectedFormula || !quantity) {
        alert('Please fill in all required fields')
        return
      }

      if (Object.keys(selectedLots).length === 0) {
        alert('Please select at least one lot')
        return
      }
    } else {
      // Repack batch
      if (!selectedRepackItem || !quantity) {
        alert('Please select an item and enter quantity')
        return
      }

      if (Object.keys(selectedLots).length === 0) {
        alert('Please select at least one input lot')
        return
      }

      // Validate that all selected lots are for the same item
      const selectedLotIds = Object.keys(selectedLots).map(id => parseInt(id))
      const lots = availableLots.filter(l => selectedLotIds.includes(l.id))
      const allSameItem = lots.every(lot => lot.item.id === selectedRepackItem.id)
      
      if (!allSameItem) {
        alert('All selected lots must be for the same item')
        return
      }
    }

    try {
      setSubmitting(true)

      const tolerance = 0.02  // Allow for kg/lbs conversion and floating point (e.g. 700.01 vs 700.00)

      // For repack: backend expects quantity_produced in the item's native unit (e.g. kg). For production: in lbs.
      let quantityProducedForApi: number
      if (batchType === 'repack' && selectedRepackItem) {
        // Quantity to repack in the repack item's native unit
        const parsedQty = parseFloat(quantity)
        const quantityInNative =
          quantityUnit === selectedRepackItem.unit_of_measure
            ? parsedQty
            : convertWeight(parsedQty, quantityUnit, selectedRepackItem.unit_of_measure as 'lbs' | 'kg')
        quantityProducedForApi = Math.round(quantityInNative * 100) / 100

        // Total quantity used is already in native unit (all repack lots are same item)
        let totalQuantityUsedNative = 0
        Object.keys(selectedLots).forEach(lotId => {
          totalQuantityUsedNative += selectedLots[parseInt(lotId)]
        })
        totalQuantityUsedNative = Math.round(totalQuantityUsedNative * 100) / 100

        if (Math.abs(totalQuantityUsedNative - quantityProducedForApi) > tolerance) {
          const uom = selectedRepackItem.unit_of_measure
          alert(`Quantity mismatch: Total quantity used (${formatNumber(totalQuantityUsedNative)} ${uom}) must equal quantity to repack (${formatNumber(quantityProducedForApi)} ${uom})`)
          setSubmitting(false)
          return
        }
      } else {
        const quantityInLbs = quantityUnit === 'kg'
          ? convertWeight(parseFloat(quantity), 'kg', 'lbs')
          : parseFloat(quantity)
        const roundedQuantityInLbs = Math.round(quantityInLbs * 100) / 100

        let totalQuantityUsedInLbs = 0
        Object.keys(selectedLots).forEach(lotId => {
          const lot = availableLots.find(l => l.id === parseInt(lotId)) || allLots.find(l => l.id === parseInt(lotId))
          if (lot) {
            const quantityUsed = selectedLots[parseInt(lotId)]
            if (lot.item.unit_of_measure === 'lbs') {
              totalQuantityUsedInLbs += quantityUsed
            } else if (lot.item.unit_of_measure === 'kg') {
              totalQuantityUsedInLbs += convertWeight(quantityUsed, 'kg', 'lbs')
            }
          }
        })
        totalQuantityUsedInLbs = Math.round(totalQuantityUsedInLbs * 100) / 100

        if (Math.abs(totalQuantityUsedInLbs - roundedQuantityInLbs) > tolerance) {
          alert(`Quantity mismatch: Total quantity used (${formatNumber(totalQuantityUsedInLbs)} lbs) must equal quantity to produce (${formatNumber(roundedQuantityInLbs)} lbs)`)
          setSubmitting(false)
          return
        }
        quantityProducedForApi = roundedQuantityInLbs
      }

      // Check if production date is in the future
      const selectedDate = new Date(productionDate)
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      selectedDate.setHours(0, 0, 0, 0)
      const isFuture = selectedDate > today

      // Batch number will be auto-generated by the backend
      const batchData: any = {
        batch_type: batchType,
        quantity_produced: quantityProducedForApi,
        production_date: productionDate,
        status: isFuture ? 'scheduled' : 'in_progress',
        inputs: Object.keys(selectedLots).map(lotId => {
          const qty = selectedLots[parseInt(lotId)]
          // Preserve exact integers, round decimals to 2 places
          // Use tolerance of 0.01 to catch floating point errors (e.g., 615.99 -> 616)
          const roundedToInteger = Math.round(qty)
          const isInteger = Math.abs(qty - roundedToInteger) <= 0.01
          return {
            lot_id: parseInt(lotId),
            quantity_used: isInteger ? roundedToInteger : Math.round(qty * 100) / 100
          }
        }),
        indirect_materials: Object.keys(selectedIndirectMaterials).map(lotId => ({
          lot_id: parseInt(lotId),
          quantity_used: selectedIndirectMaterials[parseInt(lotId)]
        }))
      }

      if (batchType === 'production') {
        batchData.finished_good_item_id = selectedFinishedGood!.id
        // Add selected partials to work in (will be processed when batch is closed)
        if (selectedPartials.size > 0) {
          batchData.work_in_partials = Array.from(selectedPartials).map(lotId => ({
            lot_id: lotId
          }))
        }
        // Record ratio changes and substitutions for audit (batch and production logs)
        if (selectedFormula?.ingredients?.length) {
          const hasPctOverride = selectedFormula.ingredients.some(ing => ingredientPercentageOverrides[ing.id] != null)
          const hasSubstitution = selectedFormula.ingredients.some(ing => {
            const o = ingredientOverrides[ing.id]
            return o && !o.useFormula && o.substituteItemId != null
          })
          if (hasPctOverride || hasSubstitution) {
            batchData.recipe_snapshot = JSON.stringify({
              formula_id: selectedFormula.id,
              finished_good_sku: selectedFinishedGood?.sku ?? null,
              finished_good_name: selectedFinishedGood?.name ?? null,
              ingredients: selectedFormula.ingredients.map((ing: { id: number; item?: { sku?: string; name?: string }; percentage: number }) => {
                const o = ingredientOverrides[ing.id]
                const batchPct = ingredientPercentageOverrides[ing.id] ?? ing.percentage
                const substituted = !!(o && !o.useFormula && o.substituteItemId != null)
                const substituteItem = substituted && repackItems ? repackItems.find((i: { id: number }) => i.id === o!.substituteItemId) : null
                return {
                  formula_ingredient_id: ing.id,
                  formula_item_sku: ing.item?.sku ?? null,
                  formula_item_name: ing.item?.name ?? null,
                  formula_pct: ing.percentage,
                  batch_pct: batchPct,
                  batch_pct_overridden: ingredientPercentageOverrides[ing.id] != null,
                  substituted,
                  substitute_item_sku: substituteItem?.sku ?? null,
                  substitute_item_name: substituteItem?.name ?? null,
                }
              }),
            })
          }
        }
      } else {
        batchData.finished_good_item_id = selectedRepackItem!.id
        if (outputPackSizeId) {
          batchData.output_pack_size_id = parseInt(outputPackSizeId)
        }
      }

      console.log('Submitting batch data:', JSON.stringify(batchData, null, 2))
      await createProductionBatch(batchData)
      
      alert(`Batch ticket created successfully!`)
      onSuccess()
    } catch (error: any) {
      console.error('Failed to create batch ticket:', error)
      console.error('Error response:', error.response)
      console.error('Error data:', error.response?.data)
      console.error('Error status:', error.response?.status)
      
      // Try to get detailed error message
      let errorMessage = 'Failed to create batch ticket'
      if (error.response?.data) {
        console.log('Full error data:', JSON.stringify(error.response.data, null, 2))
        if (error.response.data.detail) {
          errorMessage = error.response.data.detail
        } else if (error.response.data.error) {
          errorMessage = error.response.data.error
        } else if (typeof error.response.data === 'string') {
          errorMessage = error.response.data
        } else if (error.response.data.non_field_errors) {
          errorMessage = error.response.data.non_field_errors.join(', ')
        } else {
          // Try to format validation errors
          const errorParts: string[] = []
          for (const [field, messages] of Object.entries(error.response.data)) {
            if (Array.isArray(messages)) {
              errorParts.push(`${field}: ${messages.join(', ')}`)
            } else if (typeof messages === 'string') {
              errorParts.push(`${field}: ${messages}`)
            } else {
              errorParts.push(`${field}: ${JSON.stringify(messages)}`)
            }
          }
          if (errorParts.length > 0) {
            errorMessage = errorParts.join('\n')
          } else {
            // If we can't parse it, show the raw data
            errorMessage = JSON.stringify(error.response.data)
          }
        }
      } else if (error.message) {
        errorMessage = error.message
      }
      
      alert(errorMessage)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="modal-overlay">
        <div className="modal-content">
          <div className="loading">Loading...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content create-batch-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Batch Ticket</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        <form onSubmit={handleSubmit} className="batch-form">
          <div className="form-group">
            <label>Batch Type *</label>
            <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
              <button
                type="button"
                className={`toggle-btn ${batchType === 'production' ? 'active' : ''}`}
                onClick={() => {
                  setBatchType('production')
                  setSelectedFinishedGood(null)
                  setSelectedRepackItem(null)
                  setSelectedLots({})
                  setLotInputValues({})
                }}
                style={{ padding: '8px 16px', borderRadius: '4px', border: '1px solid #ccc', cursor: 'pointer' }}
              >
                Production
              </button>
              <button
                type="button"
                className={`toggle-btn ${batchType === 'repack' ? 'active' : ''}`}
                onClick={() => {
                  setBatchType('repack')
                  setSelectedFinishedGood(null)
                  setSelectedRepackItem(null)
                  setSelectedLots({})
                  setLotInputValues({})
                }}
                style={{ padding: '8px 16px', borderRadius: '4px', border: '1px solid #ccc', cursor: 'pointer' }}
              >
                Repack
              </button>
            </div>
          </div>

          {batchType === 'production' ? (
            <div className="form-group">
              <label>Finished Good *</label>
              <select
                value={selectedFinishedGood?.id || ''}
                onChange={(e) => {
                  const item = finishedGoods.find(i => i.id === parseInt(e.target.value))
                  setSelectedFinishedGood(item || null)
                }}
                required
              >
                <option value="">Select Finished Good</option>
                {finishedGoods.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.sku} - {item.name}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="form-group">
              <label>Item to Repack *</label>
              <select
                value={selectedRepackItem?.id || ''}
                onChange={(e) => {
                  const item = repackItems.find(i => i.id === parseInt(e.target.value))
                  setSelectedRepackItem(item || null)
                }}
                required
              >
                <option value="">Select Item</option>
                {repackItems.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.sku} - {item.name} ({item.item_type === 'distributed_item' ? 'Distribution' : 'Raw Material'})
                  </option>
                ))}
              </select>
            </div>
          )}

          {batchType === 'production' && selectedFormula && (
            <>
              <div className="formula-section">
                <label className="section-label">Formula (base) – you can substitute raw materials per ingredient below</label>
                <div className="formula-display">
                  <div className="formula-header">
                    <span className="formula-version">Version: {selectedFormula.version}</span>
                  </div>
                  <div className="ingredients-list">
                    {selectedFormula.ingredients.map((ingredient) => (
                      <div key={ingredient.id} className="ingredient-item">
                        <span className="ingredient-name">{ingredient.item.name}</span>
                        <span className="ingredient-percentage">{ingredient.percentage}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}

          {batchType === 'production' && selectedFinishedGood && partialLots.length > 0 && (
            <div className="form-group">
              <label className="section-label">Work In Partials (Optional)</label>
              <p className="section-hint">
                Select partial lots (quantities less than pack size) to work into this batch. 
                These will be combined with the new production when the batch is closed.
              </p>
              <div className="lots-grid" style={{ marginTop: '10px' }}>
                {partialLots.map((lot) => (
                  <div 
                    key={lot.id} 
                    className={`lot-card ${selectedPartials.has(lot.id) ? 'selected' : ''}`}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handlePartialToggle(lot.id)}
                  >
                    <div className="lot-card-header">
                      <input
                        type="checkbox"
                        checked={selectedPartials.has(lot.id)}
                        onChange={() => handlePartialToggle(lot.id)}
                        onClick={(e) => e.stopPropagation()}
                        style={{ marginRight: '8px' }}
                      />
                      <span className="lot-number-badge">{lot.lot_number}</span>
                      <span className="lot-available-badge" style={{ background: '#ffc107', color: '#000' }}>
                        Partial: {formatNumber(lot.quantity_remaining)} {lot.item.unit_of_measure}
                      </span>
                    </div>
                    <div className="lot-info">
                      <span>Received: {new Date(lot.received_date).toLocaleDateString()}</span>
                      {lot.pack_size_obj && (
                        <span>Pack Size: {formatNumber(lot.pack_size_obj.pack_size)} {lot.pack_size_obj.pack_size_unit}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="form-row">
            <div className="form-group">
              <label>{batchType === 'production' ? 'Total Quantity to Produce *' : 'Quantity to Repack *'}</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  required
                  placeholder="0.00"
                />
                <div className="unit-toggle">
                  <button
                    type="button"
                    className={`toggle-btn ${quantityUnit === 'lbs' ? 'active' : ''}`}
                    onClick={() => handleQuantityUnitChange('lbs')}
                  >
                    lbs
                  </button>
                  <button
                    type="button"
                    className={`toggle-btn ${quantityUnit === 'kg' ? 'active' : ''}`}
                    onClick={() => handleQuantityUnitChange('kg')}
                  >
                    kg
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="production-date">Production Date *</label>
            <input
              type="date"
              id="production-date"
              value={productionDate}
              onChange={(e) => setProductionDate(e.target.value)}
              className="form-input"
              min={minDateForEntry}
            />
            <small className="form-hint">
              {new Date(productionDate) > new Date() 
                ? 'Future date selected - batch will be created as "Scheduled"'
                : minDateForEntry ? 'Select today or a future date' : 'Any date allowed (backdated entry on)'}
            </small>
          </div>

          {batchType === 'production' && selectedFormula && (
              <div className="lots-section">
                <label className="section-label">Select Lots (Available from Inventory) *</label>
                {selectedFormula && (!selectedFormula.ingredients || selectedFormula.ingredients.length === 0) ? (
                  <div className="warning-message" style={{ padding: '10px', background: '#fff3cd', border: '1px solid #ffc107', borderRadius: '4px', marginBottom: '15px' }}>
                    ⚠️ This formula has no ingredients defined. Please add ingredients to the formula, or select lots from the available inventory below.
                  </div>
                ) : (
                  <p className="section-hint">Select specific lots and enter quantities to use for each ingredient</p>
                )}
                
                {availableLots.length === 0 && allLots.length > 0 && selectedFormula && selectedFormula.ingredients && selectedFormula.ingredients.length > 0 && (
                  <div className="warning-message" style={{ padding: '10px', background: '#fff3cd', border: '1px solid #ffc107', borderRadius: '4px', marginBottom: '15px' }}>
                    ⚠️ No lots match the formula ingredients. Available lots: {allLots.length}. 
                    Check console for details.
                  </div>
                )}
                
                {allLots.length === 0 && (
                  <div className="warning-message" style={{ padding: '10px', background: '#f8d7da', border: '1px solid #dc3545', borderRadius: '4px', marginBottom: '15px' }}>
                    ⚠️ No available lots found in inventory. Please check in some materials first.
                  </div>
                )}
                
                {selectedFormula.ingredients.map((ingredient) => {
                  const override = ingredientOverrides[ingredient.id]
                  const useSubstitute = override && !override.useFormula && override.substituteItemId != null
                  // Lots for this row: formula ingredient (by SKU) or substitute item (by id)
                  const ingredientLots = useSubstitute
                    ? allLots.filter((lot: Lot) => lot.item.id === override!.substituteItemId)
                    : availableLots.filter(lot => lot.item.sku === ingredient.item.sku)
                  const substituteItems = repackItems.filter(i => i.id !== ingredient.item.id)
                  // Total selected for this row only (from lots in ingredientLots)
                  let totalSelected = 0
                  ingredientLots.forEach(lot => {
                    const lotIdNum = lot.id
                    if (!selectedLots[lotIdNum]) return
                    const inputValue = lotInputValues[lotIdNum]
                    if (inputValue && quantityUnit === lot.item.unit_of_measure) {
                      if (!inputValue.includes('.')) {
                        totalSelected += parseInt(inputValue, 10)
                      } else {
                        totalSelected += parseFloat(inputValue)
                      }
                    } else {
                      const storedQty = selectedLots[lotIdNum] || 0
                      if (quantityUnit !== lot.item.unit_of_measure) {
                        totalSelected += convertWeight(storedQty, lot.item.unit_of_measure as 'lbs' | 'kg', quantityUnit)
                      } else {
                        totalSelected += storedQty
                      }
                    }
                  })
                  
                  // Format final result - if very close to an integer, use exact integer
                  // This handles floating point accumulation errors
                  let finalTotalSelected: number
                  const roundedToInteger = Math.round(totalSelected)
                  const difference = Math.abs(totalSelected - roundedToInteger)
                  
                  // If within 0.02 of an integer, treat as integer (handles floating point errors like 615.99 -> 616)
                  // This catches cases where floating point errors cause values like 615.99 or 616.01
                  if (difference <= 0.02) {
                    finalTotalSelected = roundedToInteger
                  } else {
                    // Has decimals - round to 2 places
                    finalTotalSelected = Math.round(totalSelected * 100) / 100
                  }
                  
                  // Effective % for this batch: override or formula default
                  const effectivePct = ingredientPercentageOverrides[ingredient.id] ?? ingredient.percentage
                  const baseQuantity = quantity ? parseFloat(quantity) : 0
                  const requiredQty = baseQuantity * (effectivePct / 100)
                  const requiredQtyDisplay = formatNumber(requiredQty)
                  const hasPctOverride = ingredientPercentageOverrides[ingredient.id] != null

                  return (
                    <div key={ingredient.id} className="ingredient-group">
                      <div className="ingredient-header">
                        <div className="ingredient-title">
                          <span className="ingredient-name">{ingredient.item.name}</span>
                          <span className="ingredient-percentage">
                            Formula: {ingredient.percentage}%
                            {hasPctOverride && (
                              <span className="batch-pct-override"> → Batch: {effectivePct}%</span>
                            )}
                          </span>
                        </div>
                        <div className="ingredient-batch-pct-row">
                          <label className="batch-pct-label">Batch % for this ingredient:</label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="100"
                            className="batch-pct-input"
                            value={hasPctOverride ? effectivePct : ''}
                            placeholder={String(ingredient.percentage)}
                            onChange={(e) => {
                              const raw = e.target.value.trim()
                              if (raw === '') {
                                setIngredientPercentageOverrides(prev => { const n = { ...prev }; delete n[ingredient.id]; return n })
                                return
                              }
                              const num = parseFloat(raw)
                              if (!isNaN(num) && num >= 0 && num <= 100) {
                                setIngredientPercentageOverrides(prev => ({ ...prev, [ingredient.id]: num }))
                              }
                            }}
                          />
                          <span className="batch-pct-suffix">%</span>
                          {hasPctOverride && (
                            <button
                              type="button"
                              className="btn-reset-pct"
                              onClick={() => setIngredientPercentageOverrides(prev => { const n = { ...prev }; delete n[ingredient.id]; return n })}
                            >
                              Reset to formula
                            </button>
                          )}
                        </div>
                        <div className="ingredient-summary">
                          <span className="required-qty">
                            Required: {requiredQtyDisplay} {quantityUnit === 'kg' ? 'kg' : 'lbs'}
                            {hasPctOverride && ' (from batch %)'}
                          </span>
                          <span className={`selected-qty ${finalTotalSelected > 0 ? 'has-selection' : ''}`}>
                            Selected: {formatNumber(finalTotalSelected)} {quantityUnit}
                          </span>
                        </div>
                      </div>
                      <div className="ingredient-substitute-row">
                        {!useSubstitute ? (
                          <>
                            <span className="ingredient-source">Using formula: {ingredient.item.name} ({ingredient.item.sku})</span>
                            <button
                              type="button"
                              className="btn-link-substitute"
                              onClick={() => {
                                setIngredientOverrides(prev => ({ ...prev, [ingredient.id]: { useFormula: false, substituteItemId: null } }))
                                const formulaLotIds = allLots.filter((l: Lot) => l.item.sku === ingredient.item.sku).map((l: Lot) => l.id)
                                setSelectedLots(prev => { const next = { ...prev }; formulaLotIds.forEach(id => { delete next[id] }); return next })
                                setLotInputValues(prev => { const next = { ...prev }; formulaLotIds.forEach(id => { delete next[id] }); return next })
                              }}
                            >
                              Substitute with different raw material
                            </button>
                          </>
                        ) : (
                          <>
                            <label className="substitute-label">Substitute raw material:</label>
                            <select
                              value={override?.substituteItemId ?? ''}
                              onChange={(e) => {
                                const id = e.target.value ? parseInt(e.target.value) : null
                                const prevSubId = override?.substituteItemId
                                setIngredientOverrides(prev => ({ ...prev, [ingredient.id]: { useFormula: false, substituteItemId: id } }))
                                if (prevSubId != null) {
                                  const prevLotIds = allLots.filter((l: Lot) => l.item.id === prevSubId).map((l: Lot) => l.id)
                                  setSelectedLots(prev => { const next = { ...prev }; prevLotIds.forEach(lid => { delete next[lid] }); return next })
                                  setLotInputValues(prev => { const next = { ...prev }; prevLotIds.forEach(lid => { delete next[lid] }); return next })
                                }
                              }}
                              className="substitute-select"
                            >
                              <option value="">Select item…</option>
                              {substituteItems.map(item => (
                                <option key={item.id} value={item.id}>{item.sku} – {item.name}</option>
                              ))}
                            </select>
                            <button
                              type="button"
                              className="btn-link-use-formula"
                              onClick={() => {
                                setIngredientOverrides(prev => ({ ...prev, [ingredient.id]: { useFormula: true, substituteItemId: null } }))
                                if (override?.substituteItemId != null) {
                                  const substituteLotIds = allLots.filter((l: Lot) => l.item.id === override.substituteItemId).map((l: Lot) => l.id)
                                  setSelectedLots(prev => { const next = { ...prev }; substituteLotIds.forEach(id => { delete next[id] }); return next })
                                  setLotInputValues(prev => { const next = { ...prev }; substituteLotIds.forEach(id => { delete next[id] }); return next })
                                }
                              }}
                            >
                              Use formula ingredient instead
                            </button>
                          </>
                        )}
                      </div>
                      {useSubstitute && (
                        <p className="substitute-hint">This batch uses {requiredQtyDisplay} {quantityUnit} ({effectivePct}%). Enter quantity to use for this substitute (adjust if different strength, e.g. 1% vs 0.8%).</p>
                      )}
                      
                      {ingredientLots.length === 0 ? (
                        <div className="no-lots-available">
                          {useSubstitute ? (
                            override?.substituteItemId ? (
                              <>⚠️ No available lots for {substituteItems.find(i => i.id === override.substituteItemId)?.name ?? 'selected item'}. Check in inventory or choose another substitute.</>
                            ) : (
                              <>Select a raw material above to see available lots.</>
                            )
                          ) : (
                            <>⚠️ No available lots for {ingredient.item.name}</>
                          )}
                        </div>
                      ) : (
                        <div className="lots-grid">
                          {ingredientLots.map((lot) => (
                            <div key={lot.id} className={`lot-card ${selectedLots[lot.id] ? 'selected' : ''}`}>
                              <div className="lot-card-header">
                                <span className="lot-number-badge">
                                  {lot.item.item_type === 'raw_material' && lot.vendor_lot_number 
                                    ? `Vendor Lot: ${lot.vendor_lot_number}` 
                                    : lot.lot_number}
                                </span>
                                <span className="lot-available-badge">
                                  {formatNumber(
                                    quantityUnit === lot.item.unit_of_measure
                                      ? lot.quantity_remaining
                                      : (lot.item.unit_of_measure === 'lbs'
                                          ? convertWeight(lot.quantity_remaining, 'lbs', 'kg')
                                          : convertWeight(lot.quantity_remaining, 'kg', 'lbs'))
                                  )} {quantityUnit} available
                                </span>
                              </div>
                              <div className="lot-quantity-section">
                                <label>Quantity to Use</label>
                                <div className="quantity-input-group">
                                  <input
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    max={quantityUnit === lot.item.unit_of_measure 
                                      ? lot.quantity_remaining 
                                      : (lot.item.unit_of_measure === 'lbs' 
                                          ? convertWeight(lot.quantity_remaining, 'lbs', 'kg')
                                          : convertWeight(lot.quantity_remaining, 'kg', 'lbs'))}
                                    value={lotInputValues[lot.id] || ''}
                                    onChange={(e) => handleLotQuantityChange(lot.id, e.target.value, lot.item.unit_of_measure)}
                                    placeholder="0.00"
                                    className="quantity-input"
                                  />
                                  <span className="unit-label">{quantityUnit}</span>
                                </div>
                                {selectedLots[lot.id] && (
                                  <button
                                    type="button"
                                    onClick={() => handleLotQuantityChange(lot.id, '', lot.item.unit_of_measure)}
                                    className="btn-clear-lot"
                                  >
                                    Clear
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
                {selectedFormula && (() => {
                  const totalBatchPct = selectedFormula.ingredients.reduce(
                    (sum, ing) => sum + (ingredientPercentageOverrides[ing.id] ?? ing.percentage),
                    0
                  )
                  const hasAnyPctOverride = selectedFormula.ingredients.some(ing => ingredientPercentageOverrides[ing.id] != null)
                  if (!hasAnyPctOverride) return null
                  return (
                    <div className="batch-pct-total-row">
                      <span className="batch-pct-total-label">Total batch %:</span>
                      <span className={`batch-pct-total-value ${Math.abs(totalBatchPct - 100) < 0.01 ? '' : 'batch-pct-warning'}`}>
                        {formatNumber(totalBatchPct)}%
                      </span>
                      {Math.abs(totalBatchPct - 100) >= 0.01 && (
                        <span className="batch-pct-total-hint"> (ideally 100%)</span>
                      )}
                    </div>
                  )
                })()}
              </div>
          )}

          {batchType === 'repack' && selectedRepackItem && (
            <>
              {availableOutputPackSizes.length > 0 && (
                <div className="form-group">
                  <label>Output Pack Size (Optional)</label>
                  <select
                    value={outputPackSizeId}
                    onChange={(e) => setOutputPackSizeId(e.target.value)}
                  >
                    <option value="">Use default pack size</option>
                    {availableOutputPackSizes.map((ps) => (
                      <option key={ps.id} value={ps.id}>
                        {ps.pack_size} {ps.pack_size_unit} {ps.description ? `- ${ps.description}` : ''} {ps.is_default ? '(Default)' : ''}
                      </option>
                    ))}
                  </select>
                  <small className="form-hint">
                    Select a different pack size for the repacked output lot. If not selected, the default pack size will be used.
                  </small>
                </div>
              )}
              
              <div className="lots-section">
                <label className="section-label">Select Input Lots (Available from Inventory) *</label>
                <p className="section-hint">Select lots to repack. A new lot will be created with a new lot number.</p>
              
              {availableLots.length === 0 && (
                <div className="warning-message" style={{ padding: '10px', background: '#f8d7da', border: '1px solid #dc3545', borderRadius: '4px', marginBottom: '15px' }}>
                  ⚠️ No available lots found for {selectedRepackItem.name}. Please check in some materials first.
                </div>
              )}
              
              {availableLots.length > 0 && (
                <div className="lots-grid">
                  {availableLots.map((lot) => (
                    <div key={lot.id} className={`lot-card ${selectedLots[lot.id] ? 'selected' : ''}`}>
                      <div className="lot-card-header">
                        <span className="lot-number-badge">
                          {lot.item.item_type === 'raw_material' && lot.vendor_lot_number 
                            ? `Vendor Lot: ${lot.vendor_lot_number}` 
                            : lot.lot_number}
                        </span>
                        <span className="lot-available-badge">
                          {formatNumber(lot.quantity_remaining)} {lot.item.unit_of_measure} available
                        </span>
                      </div>
                      <div className="lot-quantity-section">
                        <label>Quantity to Use</label>
                        <div className="quantity-input-group">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max={quantityUnit === lot.item.unit_of_measure 
                              ? lot.quantity_remaining 
                              : (lot.item.unit_of_measure === 'lbs' 
                                  ? convertWeight(lot.quantity_remaining, 'lbs', 'kg')
                                  : convertWeight(lot.quantity_remaining, 'kg', 'lbs'))}
                            value={lotInputValues[lot.id] || ''}
                            onChange={(e) => handleLotQuantityChange(lot.id, e.target.value, lot.item.unit_of_measure)}
                            placeholder="0.00"
                            className="quantity-input"
                          />
                          <span className="unit-label">{quantityUnit}</span>
                        </div>
                        {selectedLots[lot.id] && (
                          <button
                            type="button"
                            onClick={() => handleLotQuantityChange(lot.id, '', lot.item.unit_of_measure)}
                            className="btn-clear-lot"
                          >
                            Clear
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              </div>
            </>
          )}

          {/* Indirect Materials Section - Available for both production and repack */}
          <div className="indirect-materials-section" style={{ marginTop: '30px', paddingTop: '20px', borderTop: '2px solid #e0e0e0' }}>
            <label className="section-label">Indirect Materials (Optional)</label>
            <p className="section-hint">Select indirect materials consumed during this batch (e.g., boxes, labels, etc.)</p>
            
            {indirectMaterialLots.length === 0 ? (
              <div className="info-message" style={{ padding: '10px', background: '#d1ecf1', border: '1px solid #bee5eb', borderRadius: '4px', marginBottom: '15px' }}>
                ℹ️ No indirect materials available in inventory.
              </div>
            ) : (
              <div className="lots-grid">
                {indirectMaterialLots.map((lot) => (
                  <div key={lot.id} className={`lot-card ${selectedIndirectMaterials[lot.id] ? 'selected' : ''}`}>
                    <div className="lot-card-header">
                      <span className="lot-number-badge">
                        {lot.lot_number}
                      </span>
                      <span className="lot-available-badge">
                        {formatNumber(lot.quantity_remaining)} {lot.item.unit_of_measure} available
                      </span>
                    </div>
                    <div style={{ padding: '10px', fontSize: '14px', color: '#666' }}>
                      <strong>{lot.item.name}</strong> ({lot.item.sku})
                    </div>
                    <div className="lot-quantity-section">
                      <label>Quantity to Use</label>
                      <div className="quantity-input-group">
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max={lot.quantity_remaining}
                          value={indirectMaterialInputValues[lot.id] || ''}
                          onChange={(e) => {
                            const value = e.target.value
                            const newInputValues = { ...indirectMaterialInputValues }
                            const newSelected = { ...selectedIndirectMaterials }
                            
                            if (value === '' || parseFloat(value) <= 0 || isNaN(parseFloat(value))) {
                              delete newInputValues[lot.id]
                              delete newSelected[lot.id]
                            } else {
                              const qty = parseFloat(value)
                              if (qty <= lot.quantity_remaining) {
                                newInputValues[lot.id] = value
                                newSelected[lot.id] = qty
                              } else {
                                alert(`Cannot exceed available quantity: ${lot.quantity_remaining}`)
                                return
                              }
                            }
                            
                            setIndirectMaterialInputValues(newInputValues)
                            setSelectedIndirectMaterials(newSelected)
                          }}
                          placeholder="0.00"
                          className="quantity-input"
                        />
                        <span className="unit-label">{lot.item.unit_of_measure}</span>
                      </div>
                      {selectedIndirectMaterials[lot.id] && (
                        <button
                          type="button"
                          onClick={() => {
                            const newInputValues = { ...indirectMaterialInputValues }
                            const newSelected = { ...selectedIndirectMaterials }
                            delete newInputValues[lot.id]
                            delete newSelected[lot.id]
                            setIndirectMaterialInputValues(newInputValues)
                            setSelectedIndirectMaterials(newSelected)
                          }}
                          className="btn-clear-lot"
                        >
                          Clear
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="form-actions">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button 
              type="submit" 
              className="btn btn-primary" 
              disabled={
                submitting || 
                (batchType === 'production' && !selectedFormula) ||
                (batchType === 'repack' && !selectedRepackItem)
              }
            >
              {submitting ? 'Creating...' : `Create ${batchType === 'repack' ? 'Repack' : 'Batch'} Ticket`}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateBatchTicket

