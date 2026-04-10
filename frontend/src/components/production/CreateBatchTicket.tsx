import { useState, useEffect } from 'react'
import { getItems, getFormulas, getLots, createProductionBatch, getItemPackSizes, getPartialLots } from '../../api/inventory'
import { formatNumber } from '../../utils/formatNumber'
import { normalizeMassQuantity } from '../../utils/massQuantity'
import { formatAppDate } from '../../utils/appDateFormat'
import { useGodMode } from '../../context/GodModeContext'
import {
  getBagsPerInventoryEa,
  bagsToRolls,
  rollsToBags,
} from '../../utils/rollBagUnits'
import './CreateBatchTicket.css'

function formatApiError(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const r = err as { response?: { status?: number; data?: unknown }; config?: { url?: string }; message?: string }
    const status = r.response?.status
    const url = r.config?.url ?? ''
    const data = r.response?.data
    let snippet = ''
    if (typeof data === 'string') snippet = data.slice(0, 400)
    else if (data && typeof data === 'object') {
      try {
        snippet = JSON.stringify(data).slice(0, 400)
      } catch {
        snippet = r.message ?? ''
      }
    }
    return `HTTP ${status ?? '?'} ${url} ${snippet}`.trim()
  }
  if (err instanceof Error) return err.message
  return String(err)
}

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
  /** Net usable for production (API): after sales, on-hold, in-progress batch reservations — aligns with inventory *available*. */
  quantity_available_for_use?: number
  status: string
  received_date?: string
  pack_size_obj?: { pack_size: number; pack_size_unit: string; description?: string | null } | null
}

/** Net qty available to allocate on batch tickets (matches API quantity_available_for_use; not received qty). */
function lotNetAvailable(lot: Lot): number {
  const qAvail = lot.quantity_available_for_use
  if (qAvail != null && Number.isFinite(qAvail)) return Math.max(0, qAvail)
  const qRem = lot['quantity_remaining']
  return Math.max(0, qRem ?? 0)
}

interface CreateBatchTicketProps {
  onClose: () => void
  onSuccess: () => void
}

function normalizeSku(sku: string): string {
  return sku.trim().toUpperCase()
}

/** Production batches need a formula; list one finished-good per SKU from formula definitions (avoids duplicate SKUs from other pathways). */
function buildProductionFinishedGoodsFromFormulas(itemsData: Item[], formulasData: Formula[]): Item[] {
  const seen = new Set<string>()
  const out: Item[] = []
  for (const f of formulasData) {
    const fg = f.finished_good
    if (!fg?.id || !fg.sku) continue
    const key = normalizeSku(fg.sku)
    if (seen.has(key)) continue
    seen.add(key)
    const full = itemsData.find((i) => i.id === fg.id)
    if (full && full.item_type === 'finished_good') {
      out.push(full)
    } else if (full) {
      out.push(full)
    } else {
      out.push(fg)
    }
  }
  out.sort((a, b) => a.sku.localeCompare(b.sku))
  return out
}

function lotUsableForRepack(l: Lot): boolean {
  return !!(lotNetAvailable(l) > 0 && (!l.status || l.status === 'accepted'))
}

/**
 * Repack: one dropdown row per SKU. Include distributed + raw masters, and finished goods that have on-hand lots.
 * If multiple Item rows share a SKU, pick one: prefer an item that has stock; if several, distributed > finished_good > raw.
 */
function buildRepackItemsDeduped(itemsData: Item[], lotsData: Lot[]): Item[] {
  const eligible = itemsData.filter((i) => {
    if (i.item_type === 'distributed_item' || i.item_type === 'raw_material') return true
    if (i.item_type === 'finished_good') {
      return lotsData.some((l) => l.item.id === i.id && lotUsableForRepack(l))
    }
    return false
  })
  const bySku = new Map<string, Item[]>()
  for (const it of eligible) {
    const k = normalizeSku(it.sku)
    if (!bySku.has(k)) bySku.set(k, [])
    bySku.get(k)!.push(it)
  }
  const rankType = (it: Item) =>
    it.item_type === 'distributed_item' ? 0 : it.item_type === 'finished_good' ? 1 : 2
  const out: Item[] = []
  for (const group of bySku.values()) {
    const withStock = group.filter((it) => lotsData.some((l) => l.item.id === it.id && lotUsableForRepack(l)))
    let pick: Item
    if (withStock.length === 1) {
      pick = withStock[0]
    } else if (withStock.length > 1) {
      pick =
        withStock.find((i) => i.item_type === 'distributed_item') ||
        withStock.find((i) => i.item_type === 'finished_good') ||
        withStock.sort((a, b) => rankType(a) - rankType(b) || a.id - b.id)[0]
    } else {
      const sorted = [...group].sort((a, b) => rankType(a) - rankType(b) || a.id - b.id)
      pick = sorted[0]
    }
    out.push(pick)
  }
  out.sort((a, b) => a.sku.localeCompare(b.sku))
  return out
}

function repackOptionLabel(item: Item): string {
  if (item.item_type === 'distributed_item') return 'Distribution'
  if (item.item_type === 'finished_good') return 'Manufactured stock'
  return 'Raw material'
}

function CreateBatchTicket({ onClose, onSuccess }: CreateBatchTicketProps) {
  const { minDateForEntry } = useGodMode()
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
      const endpoints = ['GET /items/', 'GET /formulas/', 'GET /lots/'] as const
      const settled = await Promise.allSettled([getItems(), getFormulas(), getLots()])
      const failures: string[] = []
      settled.forEach((result, i) => {
        if (result.status === 'rejected') {
          failures.push(`${endpoints[i]} ${formatApiError(result.reason)}`)
        }
      })
      if (failures.length > 0) {
        console.error('CreateBatchTicket loadData failed:', failures)
        alert(
          `Failed to load data (server error). Check the Network tab and Django console.\n\n${failures.join('\n')}`
        )
        return
      }
      const itemsData = (settled[0] as PromiseFulfilledResult<Awaited<ReturnType<typeof getItems>>>).value
      const formulasData = (settled[1] as PromiseFulfilledResult<Awaited<ReturnType<typeof getFormulas>>>).value
      const lotsData = (settled[2] as PromiseFulfilledResult<Awaited<ReturnType<typeof getLots>>>).value

      console.log('Loaded lots data:', lotsData)
      console.log('Total lots received:', lotsData.length)
      
      const finishedGoods = buildProductionFinishedGoodsFromFormulas(itemsData, formulasData)
      const repackItems = buildRepackItemsDeduped(itemsData, lotsData)
      setFinishedGoods(finishedGoods)
      setRepackItems(repackItems)
      
      // Load indirect material lots
      const indirectMaterialLots = lotsData.filter((lot: Lot) => 
        lot.item.item_type === 'indirect_material' && 
        lotNetAvailable(lot) > 0 &&
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
        const hasQuantity = lotNetAvailable(lot) > 0
        
        if (!hasItem) {
          console.warn('Lot missing item:', lot)
        }
        if (!isAccepted) {
          console.log('Lot not accepted:', lot.lot_number, 'status:', lot.status)
        }
        if (!hasQuantity) {
          console.log('Lot has no remaining quantity:', lot.lot_number, 'net available:', lotNetAvailable(lot))
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
        const hasQuantity = lotNetAvailable(lot) > 0
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
        quantityRemaining: lotNetAvailable(l)
      }))
    })
    
    const filteredLots = allLots.filter((lot: Lot) => {
      const lotSku = lot.item?.sku?.trim().toUpperCase()
      const matchesSku = lotSku && ingredientSkus.includes(lotSku)
      // Status might be undefined/null for older lots, so treat as accepted if not set
      const isAccepted = !lot.status || lot.status === 'accepted'
      const hasQuantity = lotNetAvailable(lot) > 0
      
      if (matchesSku && !isAccepted) {
        console.log('Lot matches SKU but not accepted:', lot.lot_number, lot.item.sku, 'status:', lot.status)
      }
      if (matchesSku && !hasQuantity) {
        console.log('Lot matches SKU but no quantity:', lot.lot_number, lot.item.sku, 'remaining:', lotNetAvailable(lot))
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
      lots: filteredLots.map(l => ({ id: l.id, lot_number: l.lot_number, sku: l.item?.sku, qty: lotNetAvailable(l) }))
    })
    
    setAvailableLots(filteredLots)
  }

  const convertWeight = (value: number, from: 'lbs' | 'kg', to: 'lbs' | 'kg'): number => {
    if (from === to) return normalizeMassQuantity(value)
    if (from === 'lbs' && to === 'kg') {
      const converted = value / 2.20462
      return normalizeMassQuantity(Math.round(converted * 100) / 100)
    }
    if (from === 'kg' && to === 'lbs') {
      const converted = value * 2.20462
      return normalizeMassQuantity(Math.round(converted * 100) / 100)
    }
    return value
  }

  const resolveLot = (lotId: number): Lot | undefined =>
    [...availableLots, ...allLots, ...indirectMaterialLots].find((l) => l.id === lotId)

  /** Formula / repack lot inputs: quantity stored as rolls in inventory; user may enter bags when pack size defines bags/roll. */
  const handleLotQuantityChange = (lotId: number, quantity: string, lotUnitOfMeasure: string) => {
    const lot = resolveLot(lotId)
    const bagsPerRoll = lot ? getBagsPerInventoryEa(lot) : null

    const newInputValues = { ...lotInputValues }
    if (quantity === '') {
      delete newInputValues[lotId]
    } else {
      newInputValues[lotId] = quantity
    }

    const newSelectedLots = { ...selectedLots }
    if (quantity === '' || parseFloat(quantity) <= 0 || isNaN(parseFloat(quantity))) {
      delete newSelectedLots[lotId]
      setLotInputValues(newInputValues)
      setSelectedLots(newSelectedLots)
      return
    }

    if (bagsPerRoll != null && lot) {
      const bags = parseFloat(quantity)
      const maxBags = rollsToBags(lotNetAvailable(lot), bagsPerRoll)
      if (bags > maxBags + 1e-6) {
        alert(
          `Cannot exceed available bags (~${formatNumber(maxBags)} bags / ${formatNumber(lotNetAvailable(lot))} rolls). Ordering stays in rolls; enter bags used for production.`
        )
        return
      }
      newSelectedLots[lotId] = bagsToRolls(bags, bagsPerRoll)
      setLotInputValues(newInputValues)
      setSelectedLots(newSelectedLots)
      return
    }

    setLotInputValues(newInputValues)

    const parsedQuantity = parseFloat(quantity)
    if (quantityUnit === lotUnitOfMeasure) {
      const isIntegerString = !quantity.includes('.')
      if (isIntegerString) {
        newSelectedLots[lotId] = parseInt(quantity, 10)
      } else {
        const rounded = Math.round(parsedQuantity)
        const isWholeNumber = Math.abs(parsedQuantity - rounded) < 0.0000001
        if (isWholeNumber) {
          newSelectedLots[lotId] = rounded
        } else {
          newSelectedLots[lotId] = Math.round(parsedQuantity * 100) / 100
        }
      }
    } else if (lotUnitOfMeasure === 'lbs' || lotUnitOfMeasure === 'kg') {
      const quantityInLotUnit = convertWeight(parsedQuantity, quantityUnit, lotUnitOfMeasure as 'lbs' | 'kg')
      newSelectedLots[lotId] = quantityInLotUnit
    } else {
      newSelectedLots[lotId] = Math.round(parsedQuantity * 100) / 100
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
      if (lot && getBagsPerInventoryEa(lot) != null && lotInputValues[lotId] !== undefined) {
        convertedInputValues[lotId] = lotInputValues[lotId]
        if (selectedLots[lotId] != null) convertedStoredValues[lotId] = selectedLots[lotId]
        return
      }
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

  const handleIndirectQuantityChange = (lot: Lot, value: string) => {
    const lotId = lot.id
    const bpr = getBagsPerInventoryEa(lot)
    const newInputValues = { ...indirectMaterialInputValues }
    const newSelected = { ...selectedIndirectMaterials }

    if (value === '' || parseFloat(value) <= 0 || isNaN(parseFloat(value))) {
      delete newInputValues[lotId]
      delete newSelected[lotId]
      setIndirectMaterialInputValues(newInputValues)
      setSelectedIndirectMaterials(newSelected)
      return
    }

    if (bpr != null) {
      const bags = parseFloat(value)
      const maxBags = rollsToBags(lotNetAvailable(lot), bpr)
      if (bags > maxBags + 1e-6) {
        alert(
          `Cannot exceed available bags (~${formatNumber(maxBags)} bags / ${formatNumber(lotNetAvailable(lot))} rolls).`
        )
        return
      }
      newInputValues[lotId] = value
      newSelected[lotId] = bagsToRolls(bags, bpr)
      setIndirectMaterialInputValues(newInputValues)
      setSelectedIndirectMaterials(newSelected)
      return
    }

    const qty = parseFloat(value)
    if (qty <= lotNetAvailable(lot)) {
      newInputValues[lotId] = value
      newSelected[lotId] = qty
      setIndirectMaterialInputValues(newInputValues)
      setSelectedIndirectMaterials(newSelected)
    } else {
      alert(`Cannot exceed available quantity: ${lotNetAvailable(lot)}`)
    }
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
        quantityProducedForApi = normalizeMassQuantity(Math.round(quantityInNative * 100) / 100)

        // Total quantity used is already in native unit (all repack lots are same item)
        let totalQuantityUsedNative = 0
        Object.keys(selectedLots).forEach(lotId => {
          totalQuantityUsedNative += selectedLots[parseInt(lotId)]
        })
        totalQuantityUsedNative = normalizeMassQuantity(Math.round(totalQuantityUsedNative * 100) / 100)

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
        const roundedQuantityInLbs = normalizeMassQuantity(Math.round(quantityInLbs * 100) / 100)

        let totalQuantityUsedInLbs = 0
        Object.keys(selectedLots).forEach(lotId => {
          const lot = availableLots.find(l => l.id === parseInt(lotId)) || allLots.find(l => l.id === parseInt(lotId))
          if (lot) {
            const quantityUsed = selectedLots[parseInt(lotId)]
            if (lot.item.unit_of_measure === 'lbs') {
              totalQuantityUsedInLbs += quantityUsed
            } else if (lot.item.unit_of_measure === 'kg') {
              totalQuantityUsedInLbs += convertWeight(quantityUsed, 'kg', 'lbs')
            } else if (lot.item.unit_of_measure === 'ea') {
              // Matches backend: ea counts 1:1 toward batch lbs balance for production validation
              totalQuantityUsedInLbs += quantityUsed
            }
          }
        })
        totalQuantityUsedInLbs = normalizeMassQuantity(Math.round(totalQuantityUsedInLbs * 100) / 100)

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
        batch_ticket_mass_unit: quantityUnit,
        quantity_produced: quantityProducedForApi,
        production_date: productionDate,
        status: isFuture ? 'scheduled' : 'in_progress',
        inputs: Object.keys(selectedLots).map(lotId => {
          const qty = selectedLots[parseInt(lotId)]
          const lot = availableLots.find(l => l.id === parseInt(lotId)) || allLots.find(l => l.id === parseInt(lotId))
          if (lot?.item.unit_of_measure === 'ea') {
            return {
              lot_id: parseInt(lotId),
              quantity_used: Math.round(qty * 1e5) / 1e5,
            }
          }
          const roundedToInteger = Math.round(qty)
          const isInteger = Math.abs(qty - roundedToInteger) <= 0.01
          return {
            lot_id: parseInt(lotId),
            quantity_used: isInteger ? roundedToInteger : Math.round(qty * 100) / 100
          }
        }),
        indirect_materials: Object.keys(selectedIndirectMaterials).map(lotId => {
          const id = parseInt(lotId)
          const q = selectedIndirectMaterials[id]
          const lot = indirectMaterialLots.find(l => l.id === id)
          const qtyOut =
            lot?.item.unit_of_measure === 'ea' ? Math.round(q * 1e5) / 1e5 : Math.round(q * 100) / 100
          return { lot_id: id, quantity_used: qtyOut }
        })
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
                    {item.sku} - {item.name} ({repackOptionLabel(item)})
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
              <div className="lots-list" style={{ marginTop: '10px' }}>
                {partialLots.map((lot) => {
                  const partialBpr = getBagsPerInventoryEa(lot)
                  return (
                  <div 
                    key={lot.id} 
                    className={`lot-row lot-row--partial ${selectedPartials.has(lot.id) ? 'selected' : ''}`}
                    style={{ cursor: 'pointer' }}
                    onClick={() => handlePartialToggle(lot.id)}
                  >
                    <div className="lot-row-partial-main">
                      <input
                        type="checkbox"
                        checked={selectedPartials.has(lot.id)}
                        onChange={() => handlePartialToggle(lot.id)}
                        onClick={(e) => e.stopPropagation()}
                        style={{ marginRight: '4px', flexShrink: 0 }}
                      />
                      <span className="lot-number-badge">{lot.lot_number}</span>
                      <span className="lot-available-badge" style={{ background: '#ffc107', color: '#000' }}>
                        Partial:{' '}
                        {partialBpr != null
                          ? `${formatNumber(lotNetAvailable(lot))} rolls (~${formatNumber(rollsToBags(lotNetAvailable(lot), partialBpr))} bags)`
                          : `${formatNumber(lotNetAvailable(lot))} ${lot.item.unit_of_measure}`}
                      </span>
                    </div>
                    <div className="lot-row-partial-meta">
                      <span>Received: {formatAppDate(lot.received_date)}</span>
                      {lot.pack_size_obj && (
                        <span>Pack Size: {formatNumber(lot.pack_size_obj.pack_size)} {lot.pack_size_obj.pack_size_unit}</span>
                      )}
                    </div>
                  </div>
                  )
                })}
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
                : minDateForEntry ? 'Select today or a future date' : 'Any date allowed (God mode on)'}
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
                  let selectedBagsTotal = 0
                  ingredientLots.forEach(lot => {
                    const lotIdNum = lot.id
                    if (!selectedLots[lotIdNum]) return
                    const bpr = getBagsPerInventoryEa(lot)
                    if (bpr != null) {
                      selectedBagsTotal += rollsToBags(selectedLots[lotIdNum], bpr)
                      return
                    }
                    const inputValue = lotInputValues[lotIdNum]
                    if (inputValue && quantityUnit === lot.item.unit_of_measure) {
                      if (!inputValue.includes('.')) {
                        totalSelected += parseInt(inputValue, 10)
                      } else {
                        totalSelected += parseFloat(inputValue)
                      }
                    } else {
                      const storedQty = selectedLots[lotIdNum] || 0
                      if (lot.item.unit_of_measure !== 'lbs' && lot.item.unit_of_measure !== 'kg') {
                        totalSelected += storedQty
                      } else if (quantityUnit !== lot.item.unit_of_measure) {
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
                          <span className={`selected-qty ${finalTotalSelected > 0 || selectedBagsTotal > 0 ? 'has-selection' : ''}`}>
                            {selectedBagsTotal > 0 && (
                              <span className="selected-bags">Bags (from rolls): {formatNumber(selectedBagsTotal)}</span>
                            )}
                            {selectedBagsTotal > 0 && finalTotalSelected > 0 && ' · '}
                            {finalTotalSelected > 0 && (
                              <span>Selected (weight): {formatNumber(finalTotalSelected)} {quantityUnit}</span>
                            )}
                            {selectedBagsTotal > 0 && finalTotalSelected === 0 && (
                              <span> (inventory deducted in rolls)</span>
                            )}
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
                        <div className="lots-list">
                          {ingredientLots.map((lot) => {
                            const bpr = getBagsPerInventoryEa(lot)
                            const maxBagsAvail = bpr != null ? rollsToBags(lotNetAvailable(lot), bpr) : null
                            const displayAvail =
                              bpr != null
                                ? `${formatNumber(lotNetAvailable(lot))} rolls (~${formatNumber(maxBagsAvail ?? 0)} bags)`
                                : `${formatNumber(
                                    quantityUnit === lot.item.unit_of_measure
                                      ? lotNetAvailable(lot)
                                      : lot.item.unit_of_measure === 'lbs'
                                        ? convertWeight(lotNetAvailable(lot), 'lbs', 'kg')
                                        : lot.item.unit_of_measure === 'kg'
                                          ? convertWeight(lotNetAvailable(lot), 'kg', 'lbs')
                                          : lotNetAvailable(lot)
                                  )} ${quantityUnit} available`
                            const maxInput =
                              bpr != null
                                ? maxBagsAvail ?? 0
                                : quantityUnit === lot.item.unit_of_measure
                                  ? lotNetAvailable(lot)
                                  : lot.item.unit_of_measure === 'lbs'
                                    ? convertWeight(lotNetAvailable(lot), 'lbs', 'kg')
                                    : lot.item.unit_of_measure === 'kg'
                                      ? convertWeight(lotNetAvailable(lot), 'kg', 'lbs')
                                      : lotNetAvailable(lot)
                            return (
                            <div key={lot.id} className={`lot-row ${selectedLots[lot.id] ? 'selected' : ''}`}>
                              <div className="lot-row-ident">
                                <span className="lot-number-badge">
                                  {lot.item.item_type === 'raw_material' && lot.vendor_lot_number 
                                    ? `Vendor Lot: ${lot.vendor_lot_number}` 
                                    : lot.lot_number}
                                </span>
                                <span className="lot-available-inline">{displayAvail}</span>
                              </div>
                              <div className="lot-row-qty">
                                <label>{bpr != null ? 'Bags to use' : 'Quantity to use'}</label>
                                {bpr != null && (
                                  <p className="ea-bag-hint">
                                    Stock &amp; POs are in rolls ({formatNumber(bpr)} bags/roll). Enter bags consumed; the system converts to rolls.
                                  </p>
                                )}
                                <div className="quantity-input-group">
                                  <input
                                    type="number"
                                    step={bpr != null ? '1' : '0.01'}
                                    min="0"
                                    max={maxInput}
                                    value={lotInputValues[lot.id] || ''}
                                    onChange={(e) => handleLotQuantityChange(lot.id, e.target.value, lot.item.unit_of_measure)}
                                    placeholder={bpr != null ? '0' : '0.00'}
                                    className="quantity-input"
                                  />
                                  <span className="unit-label">{bpr != null ? 'bags' : quantityUnit}</span>
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
                            )
                          })}
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
                <div className="lots-list">
                  {availableLots.map((lot) => {
                    const bpr = getBagsPerInventoryEa(lot)
                    const maxBagsAvail = bpr != null ? rollsToBags(lotNetAvailable(lot), bpr) : null
                    const displayAvail =
                      bpr != null
                        ? `${formatNumber(lotNetAvailable(lot))} rolls (~${formatNumber(maxBagsAvail ?? 0)} bags)`
                        : `${formatNumber(
                            quantityUnit === lot.item.unit_of_measure
                              ? lotNetAvailable(lot)
                              : lot.item.unit_of_measure === 'lbs'
                                ? convertWeight(lotNetAvailable(lot), 'lbs', 'kg')
                                : lot.item.unit_of_measure === 'kg'
                                  ? convertWeight(lotNetAvailable(lot), 'kg', 'lbs')
                                  : lotNetAvailable(lot)
                          )} ${quantityUnit} available`
                    const maxInput =
                      bpr != null
                        ? maxBagsAvail ?? 0
                        : quantityUnit === lot.item.unit_of_measure
                          ? lotNetAvailable(lot)
                          : lot.item.unit_of_measure === 'lbs'
                            ? convertWeight(lotNetAvailable(lot), 'lbs', 'kg')
                            : lot.item.unit_of_measure === 'kg'
                              ? convertWeight(lotNetAvailable(lot), 'kg', 'lbs')
                              : lotNetAvailable(lot)
                    return (
                    <div key={lot.id} className={`lot-row ${selectedLots[lot.id] ? 'selected' : ''}`}>
                      <div className="lot-row-ident">
                        <span className="lot-number-badge">
                          {lot.item.item_type === 'raw_material' && lot.vendor_lot_number 
                            ? `Vendor Lot: ${lot.vendor_lot_number}` 
                            : lot.lot_number}
                        </span>
                        <span className="lot-available-inline">{displayAvail}</span>
                      </div>
                      <div className="lot-row-qty">
                        <label>{bpr != null ? 'Bags to use' : 'Quantity to use'}</label>
                        {bpr != null && (
                          <p className="ea-bag-hint">
                            Stock &amp; POs are in rolls ({formatNumber(bpr)} bags/roll). Enter bags to repack.
                          </p>
                        )}
                        <div className="quantity-input-group">
                          <input
                            type="number"
                            step={bpr != null ? '1' : '0.01'}
                            min="0"
                            max={maxInput}
                            value={lotInputValues[lot.id] || ''}
                            onChange={(e) => handleLotQuantityChange(lot.id, e.target.value, lot.item.unit_of_measure)}
                            placeholder={bpr != null ? '0' : '0.00'}
                            className="quantity-input"
                          />
                          <span className="unit-label">{bpr != null ? 'bags' : quantityUnit}</span>
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
                    )
                  })}
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
              <div className="lots-list">
                {indirectMaterialLots.map((lot) => {
                  const bpr = getBagsPerInventoryEa(lot)
                  const maxBags = bpr != null ? rollsToBags(lotNetAvailable(lot), bpr) : null
                  const availLabel =
                    bpr != null
                      ? `${formatNumber(lotNetAvailable(lot))} rolls (~${formatNumber(maxBags ?? 0)} bags)`
                      : `${formatNumber(lotNetAvailable(lot))} ${lot.item.unit_of_measure} available`
                  return (
                  <div key={lot.id} className={`lot-row ${selectedIndirectMaterials[lot.id] ? 'selected' : ''}`}>
                    <div className="lot-row-ident lot-row-ident-indirect">
                      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.5rem 0.75rem' }}>
                        <span className="lot-number-badge">{lot.lot_number}</span>
                        <span className="lot-available-inline">{availLabel}</span>
                      </div>
                      <span className="lot-row-indirect-sku">{lot.item.name} ({lot.item.sku})</span>
                    </div>
                    <div className="lot-row-qty">
                      <label>{bpr != null ? 'Bags to use' : 'Quantity to use'}</label>
                      {bpr != null && (
                        <p className="ea-bag-hint">
                          Order &amp; receive in rolls ({formatNumber(bpr)} bags/roll). Enter bags used here.
                        </p>
                      )}
                      <div className="quantity-input-group">
                        <input
                          type="number"
                          step={bpr != null ? '1' : '0.01'}
                          min="0"
                          max={bpr != null ? maxBags ?? undefined : lotNetAvailable(lot)}
                          value={indirectMaterialInputValues[lot.id] || ''}
                          onChange={(e) => handleIndirectQuantityChange(lot, e.target.value)}
                          placeholder={bpr != null ? '0' : '0.00'}
                          className="quantity-input"
                        />
                        <span className="unit-label">{bpr != null ? 'bags' : lot.item.unit_of_measure}</span>
                      </div>
                      {selectedIndirectMaterials[lot.id] && (
                        <button
                          type="button"
                          onClick={() => handleIndirectQuantityChange(lot, '')}
                          className="btn-clear-lot"
                        >
                          Clear
                        </button>
                      )}
                    </div>
                  </div>
                  )
                })}
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

