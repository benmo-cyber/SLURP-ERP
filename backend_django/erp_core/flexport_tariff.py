"""
Flexport Tariff Integration
Updates tariff rates for items using Flexport API
Runs every Sunday night via cron job
"""
import os
import sys
import django
from pathlib import Path
import requests
from datetime import datetime
import logging

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from erp_core.models import Item, CostMaster

logger = logging.getLogger(__name__)

# Flexport credentials (from Sensitive folder)
FLEXPORT_URL = "https://tariffs.flexport.com/"
FLEXPORT_USERNAME = "ben.morris@wildwoodingredients.com"
FLEXPORT_PASSWORD = "QrF8055!."


def get_tariff_from_flexport(hts_code: str, country_of_origin: str) -> float:
    """
    Query Flexport API for tariff rate
    
    Args:
        hts_code: HTS (Harmonized Tariff Schedule) code
        country_of_origin: Country of origin code
        
    Returns:
        Tariff rate as decimal (e.g., 0.381 for 38.1%)
    """
    try:
        # Note: This is a placeholder implementation
        # The actual Flexport API endpoint and authentication method may vary
        # You'll need to check Flexport's API documentation for the exact endpoint
        
        # For now, we'll use a session-based approach
        session = requests.Session()
        
        # Login to Flexport
        login_data = {
            'username': FLEXPORT_USERNAME,
            'password': FLEXPORT_PASSWORD
        }
        
        # Attempt to authenticate (adjust endpoint as needed)
        login_response = session.post(
            f"{FLEXPORT_URL}api/login",
            json=login_data,
            timeout=30
        )
        
        if login_response.status_code != 200:
            logger.error(f"Flexport login failed: {login_response.status_code}")
            return None
        
        # Query tariff endpoint (adjust endpoint as needed)
        tariff_response = session.get(
            f"{FLEXPORT_URL}api/tariffs",
            params={
                'hts_code': hts_code,
                'country_of_origin': country_of_origin
            },
            timeout=30
        )
        
        if tariff_response.status_code == 200:
            data = tariff_response.json()
            # Extract tariff rate from response (adjust field name as needed)
            tariff_rate = data.get('tariff_rate', 0.0)
            # Convert percentage to decimal if needed
            if tariff_rate > 1:
                tariff_rate = tariff_rate / 100
            return tariff_rate
        else:
            logger.warning(f"Flexport tariff query failed: {tariff_response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error querying Flexport for HTS {hts_code}, Origin {country_of_origin}: {str(e)}")
        return None


def update_tariffs():
    """
    Update tariff rates for all items with HTS codes and country of origin
    Runs every Sunday night
    """
    logger.info("Starting Flexport tariff update...")
    
    # Get all items that have HTS code and country of origin
    items_to_update = Item.objects.filter(
        hts_code__isnull=False,
        country_of_origin__isnull=False
    ).exclude(
        hts_code='',
        country_of_origin=''
    )
    
    updated_count = 0
    error_count = 0
    
    for item in items_to_update:
        try:
            # Get tariff from Flexport
            tariff_rate = get_tariff_from_flexport(item.hts_code, item.country_of_origin)
            
            if tariff_rate is not None:
                # Update item tariff
                old_tariff = item.tariff
                item.tariff = tariff_rate
                item.save()
                
                # Also update CostMaster if it exists
                cost_masters = CostMaster.objects.filter(wwi_product_code=item.sku)
                for cm in cost_masters:
                    cm.tariff = tariff_rate
                    cm.save()
                    # Recalculate landed cost
                    cm.calculate_landed_cost()
                    cm.save()
                
                logger.info(f"Updated tariff for {item.sku}: {old_tariff} -> {tariff_rate}")
                updated_count += 1
            else:
                logger.warning(f"Could not get tariff for {item.sku} (HTS: {item.hts_code}, Origin: {item.country_of_origin})")
                error_count += 1
                
        except Exception as e:
            logger.error(f"Error updating tariff for {item.sku}: {str(e)}")
            error_count += 1
    
    logger.info(f"Flexport tariff update complete: {updated_count} updated, {error_count} errors")
    return updated_count, error_count


if __name__ == '__main__':
    # Run the update
    updated, errors = update_tariffs()
    print(f"Updated {updated} items, {errors} errors")
