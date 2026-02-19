# Tariff Flow Documentation

## Overview
The tariff flow has been reworked to automatically query the Flexport Tariff Simulator API for duty rates and populate them in the Cost Master list. Tariffs are automatically refreshed every Sunday at 2am, and can be manually refreshed at any time via the "Refresh Tariffs" button.

## Components

### 1. Flexport Tariff Integration (`erp_core/flexport_tariff.py`)

**Function: `get_tariff_from_flexport(hts_code, country_of_origin)`**
- Queries Flexport Tariff Simulator API for duty rate
- Uses HTS code and country of origin to get the duty rate
- Returns tariff as decimal (e.g., 0.381 for 38.1%)
- Handles various response formats from Flexport API

**Function: `update_tariffs()`**
- Updates tariff rates for all items with HTS codes and country of origin
- Updates both `Item` and `CostMaster` records
- Recalculates landed costs automatically
- Returns count of updated items and errors

### 2. Item Creation Flow (`erp_core/views.py` - `ItemViewSet.create`)

**Process:**
1. When an item is created with HTS code and country of origin:
   - Automatically queries Flexport Tariff Simulator for duty rate
   - If successful, populates `item.tariff` and `cost_master.tariff`
   - If Flexport lookup fails, uses provided tariff value or defaults to 0
2. CostMaster is created/updated with:
   - Tariff percentage from Flexport (or provided value)
   - HTS code and country of origin
   - Landed cost calculated using: `(Price per kg * (1 + Tariff)) + Freight per kg`

### 3. Item Update Flow (`erp_core/views.py` - `ItemViewSet.update`)

**Process:**
1. If HTS code or country of origin is updated:
   - Re-queries Flexport Tariff Simulator for new duty rate
   - Updates both `Item` and `CostMaster` records
   - Recalculates landed costs
2. If tariff is manually provided:
   - Uses provided tariff value
   - Updates both records and recalculates landed costs

### 4. Manual Tariff Refresh (`erp_core/views.py` - `CostMasterViewSet.refresh_tariffs`)

**API Endpoint:** `POST /api/cost-master/refresh_tariffs/`

**Process:**
- Calls `update_tariffs()` function
- Updates all items with HTS codes and country of origin
- Returns count of updated items and errors
- Frontend button triggers this endpoint

### 5. Scheduled Tariff Refresh

**Django Management Command:** `python manage.py refresh_tariffs`
- Located in: `erp_core/management/commands/refresh_tariffs.py`
- Can be run manually or scheduled

**Windows Task Scheduler Setup:**
1. Open Windows Task Scheduler
2. Create a new task
3. Set trigger: Weekly, Sunday, 2:00 AM
4. Set action: Start a program
5. Program: `schedule_tariff_refresh.bat` (located in `backend_django/`)

**Batch File:** `schedule_tariff_refresh.bat`
- Activates virtual environment
- Runs Django management command
- Logs results

## Landed Cost Calculation

**Formula:** `(Price per kg * (1 + Tariff)) + Freight per kg`

This formula is applied in:
- `CostMaster.calculate_landed_cost()` method
- Automatically called when tariff is updated
- Ensures landed costs always reflect current tariff rates

## Frontend Integration

**Cost Master List Page:**
- "🔄 Refresh Tariffs" button in header
- Shows loading state during refresh
- Displays success/error messages
- Automatically refreshes list after update

## Error Handling

- Network errors are logged but don't stop the process
- Items that fail to update are counted in error_count
- Flexport API failures fall back to provided tariff values
- All errors are logged for debugging

## Notes

- Tariff rates are stored as decimals (0.381 = 38.1%)
- Only items with both HTS code and country of origin are updated
- CostMaster records are updated for all vendors with matching SKU
- Landed costs are automatically recalculated whenever tariff changes
