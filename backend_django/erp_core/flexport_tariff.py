"""
Flexport Tariff Integration
Updates tariff rates for items using Flexport Tariff Simulator API
Runs every Sunday night via cron job

IMPORTANT: The Flexport API endpoint and authentication method need to be configured.
The current implementation uses placeholder endpoints that may not work.
Contact Flexport support or check your Flexport dashboard for the correct API endpoint.
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

# Flexport API Configuration
# Flexport uses GraphQL API at https://api.flexport.com
# Authentication typically requires an API token (not username/password)
# 
# To get your API token:
# 1. Log into your Flexport account
# 2. Go to Settings > API Access or Developer Portal
# 3. Generate an API token
# 4. Set it below or as an environment variable
FLEXPORT_API_URL = "https://api.flexport.com"
FLEXPORT_USERNAME = "ben.morris@wildwoodingredients.com"
FLEXPORT_PASSWORD = "QrF8055!."

# Set this if you have a Flexport API token (recommended)
# You can also set it as an environment variable: FLEXPORT_API_TOKEN
FLEXPORT_API_TOKEN = os.environ.get('FLEXPORT_API_TOKEN', None)


def get_tariff_from_flexport(hts_code: str, country_of_origin: str) -> float:
    """
    Query Flexport Tariff Simulator API for duty rate
    
    Args:
        hts_code: HTS (Harmonized Tariff Schedule) code
        country_of_origin: Country of origin code (ISO 2-letter or 3-letter code)
        
    Returns:
        Tariff rate as decimal (e.g., 0.381 for 38.1%), or None if lookup fails
    """
    import sys
    
    try:
        print(f"Attempting to query Flexport for HTS {hts_code}, Origin {country_of_origin}", file=sys.stderr)
        
        # Try multiple Flexport API approaches
        # Approach 1: GraphQL API with API token (most common for Flexport)
        if FLEXPORT_API_TOKEN:
            headers = {
                'Authorization': f'Bearer {FLEXPORT_API_TOKEN}',
                'Content-Type': 'application/json'
            }
            
            # Flexport GraphQL query for tariff lookup
            graphql_query = """
            query GetTariff($htsCode: String!, $originCountry: String!) {
                tariff(htsCode: $htsCode, originCountry: $originCountry) {
                    dutyRate
                    rate
                }
            }
            """
            
            graphql_variables = {
                'htsCode': hts_code,
                'originCountry': country_of_origin
            }
            
            print(f"Attempting GraphQL query to {FLEXPORT_API_URL}/graphql", file=sys.stderr)
            response = requests.post(
                f"{FLEXPORT_API_URL}/graphql",
                json={'query': graphql_query, 'variables': graphql_variables},
                headers=headers,
                timeout=30
            )
            
            print(f"GraphQL response status: {response.status_code}", file=sys.stderr)
            
            if response.status_code == 200:
                data = response.json()
                print(f"GraphQL response data: {data}", file=sys.stderr)
                
                if 'data' in data and 'tariff' in data['data'] and data['data']['tariff']:
                    tariff_data = data['data']['tariff']
                    tariff_rate = tariff_data.get('dutyRate') or tariff_data.get('rate')
                    if tariff_rate is not None:
                        tariff_rate = float(tariff_rate)
                        if tariff_rate > 1:
                            tariff_rate = tariff_rate / 100
                        if 0 <= tariff_rate <= 1:
                            print(f"Successfully retrieved tariff via GraphQL: {tariff_rate} ({tariff_rate * 100:.2f}%)", file=sys.stderr)
                            logger.info(f"Successfully retrieved tariff for HTS {hts_code}, Origin {country_of_origin}: {tariff_rate}")
                            return tariff_rate
                elif 'errors' in data:
                    error_msg = f"GraphQL errors: {data['errors']}"
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    logger.warning(error_msg)
            else:
                print(f"GraphQL request failed: {response.status_code} - {response.text[:500]}", file=sys.stderr)
        
        # Approach 2: REST API with API token
        if FLEXPORT_API_TOKEN:
            headers = {
                'Authorization': f'Bearer {FLEXPORT_API_TOKEN}',
                'Content-Type': 'application/json'
            }
            
            print(f"Attempting REST API query to {FLEXPORT_API_URL}/v1/tariffs", file=sys.stderr)
            response = requests.get(
                f"{FLEXPORT_API_URL}/v1/tariffs",
                params={
                    'hts_code': hts_code,
                    'country_of_origin': country_of_origin,
                    'destination_country': 'US'
                },
                headers=headers,
                timeout=30
            )
            
            print(f"REST API response status: {response.status_code}", file=sys.stderr)
            
            if response.status_code == 200:
                data = response.json()
                print(f"REST API response data: {data}", file=sys.stderr)
                
                tariff_rate = data.get('duty_rate') or data.get('rate') or data.get('tariff_rate')
                if tariff_rate is not None:
                    tariff_rate = float(tariff_rate)
                    if tariff_rate > 1:
                        tariff_rate = tariff_rate / 100
                    if 0 <= tariff_rate <= 1:
                        print(f"Successfully retrieved tariff via REST API: {tariff_rate} ({tariff_rate * 100:.2f}%)", file=sys.stderr)
                        logger.info(f"Successfully retrieved tariff for HTS {hts_code}, Origin {country_of_origin}: {tariff_rate}")
                        return tariff_rate
        
        # Approach 3: Try legacy endpoint (likely won't work but worth trying)
        session = requests.Session()
        login_data = {
            'username': FLEXPORT_USERNAME,
            'password': FLEXPORT_PASSWORD
        }
        
        print(f"Attempting legacy login to {FLEXPORT_API_URL}/auth/login", file=sys.stderr)
        login_response = session.post(
            f"{FLEXPORT_API_URL}/auth/login",
            json=login_data,
            timeout=30
        )
        
        print(f"Login response status: {login_response.status_code}", file=sys.stderr)
        
        if login_response.status_code == 200:
            # If login succeeds, try to get tariff
            tariff_response = session.get(
                f"{FLEXPORT_API_URL}/v1/tariffs",
                params={
                    'hts_code': hts_code,
                    'country_of_origin': country_of_origin,
                    'destination_country': 'US'
                },
                timeout=30
            )
            
            print(f"Tariff query response status: {tariff_response.status_code}", file=sys.stderr)
            
            if tariff_response.status_code == 200:
                try:
                    data = tariff_response.json()
                    print(f"Response data: {data}", file=sys.stderr)
                except Exception as e:
                    error_msg = f"Failed to parse JSON response: {str(e)}. Response text: {tariff_response.text[:500]}"
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    logger.error(error_msg)
                    return None
                
                # Extract duty rate from response
                tariff_rate = None
                if 'duty_rate' in data:
                    tariff_rate = data['duty_rate']
                elif 'rate' in data:
                    tariff_rate = data['rate']
                elif 'tariff_rate' in data:
                    tariff_rate = data['tariff_rate']
                elif 'result' in data and isinstance(data['result'], dict):
                    if 'duty_rate' in data['result']:
                        tariff_rate = data['result']['duty_rate']
                    elif 'rate' in data['result']:
                        tariff_rate = data['result']['rate']
                
                if tariff_rate is not None:
                    tariff_rate = float(tariff_rate)
                    if tariff_rate > 1:
                        tariff_rate = tariff_rate / 100
                    if 0 <= tariff_rate <= 1:
                        print(f"Successfully retrieved tariff: {tariff_rate} ({tariff_rate * 100:.2f}%)", file=sys.stderr)
                        logger.info(f"Successfully retrieved tariff for HTS {hts_code}, Origin {country_of_origin}: {tariff_rate}")
                        return tariff_rate
                    else:
                        error_msg = f"Tariff rate out of valid range (0-1): {tariff_rate}"
                        print(f"ERROR: {error_msg}", file=sys.stderr)
                        logger.warning(error_msg)
                        return None
                else:
                    error_msg = f"Could not extract tariff rate from Flexport response: {data}"
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    logger.warning(error_msg)
                    return None
            else:
                error_msg = f"Flexport tariff query failed: {tariff_response.status_code} - {tariff_response.text[:500]}"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                logger.warning(error_msg)
                return None
        else:
            # All authentication methods failed
            if login_response.status_code in [403, 422]:
                error_msg = (
                    f"Flexport API authentication failed ({login_response.status_code}).\n\n"
                    f"The Flexport API requires an API token for authentication, not username/password.\n\n"
                    f"To fix this:\n"
                    f"1. Log into your Flexport account at https://app.flexport.com\n"
                    f"2. Go to Settings > API Access (or Developer Portal)\n"
                    f"3. Generate an API token\n"
                    f"4. Set it as an environment variable: FLEXPORT_API_TOKEN=your_token_here\n"
                    f"   OR update FLEXPORT_API_TOKEN in backend_django/erp_core/flexport_tariff.py\n\n"
                    f"Until the API token is configured, you can manually enter tariff rates in the Cost Master.\n\n"
                    f"Response: {login_response.text[:500]}"
                )
            else:
                error_msg = f"Flexport authentication failed: {login_response.status_code} - {login_response.text[:500]}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            logger.error(error_msg)
            return None
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Network error querying Flexport for HTS {hts_code}, Origin {country_of_origin}: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        logger.error(error_msg, exc_info=True)
        return None
    except Exception as e:
        error_msg = f"Error querying Flexport for HTS {hts_code}, Origin {country_of_origin}: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        logger.error(error_msg, exc_info=True)
        return None


def update_tariffs():
    """
    Update tariff rates for all items with HTS codes and country of origin
    Updates both Item and CostMaster records, and recalculates landed costs
    This function is called by the scheduled task (Sunday 2am) and the manual refresh button
    
    Returns:
        tuple: (updated_count, error_count, error_details)
    """
    import sys
    print("Starting Flexport tariff update...", file=sys.stderr)
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
    error_details = []
    
    item_count = items_to_update.count()
    print(f"Found {item_count} items to update", file=sys.stderr)
    logger.info(f"Found {item_count} items to update")
    
    # Check if API token is configured
    if not FLEXPORT_API_TOKEN:
        error_msg = (
            "FLEXPORT_API_TOKEN is not configured. "
            "Please set it as an environment variable or in flexport_tariff.py. "
            "Check your Flexport dashboard for API credentials."
        )
        print(f"WARNING: {error_msg}", file=sys.stderr)
        logger.warning(error_msg)
        error_details.append(error_msg)
    
    for item in items_to_update:
        try:
            print(f"Processing {item.sku}: HTS={item.hts_code}, Origin={item.country_of_origin}", file=sys.stderr)
            # Query Flexport Tariff Simulator for duty rate
            tariff_rate = get_tariff_from_flexport(item.hts_code, item.country_of_origin)
            
            if tariff_rate is not None:
                # Update item tariff
                old_tariff = item.tariff
                item.tariff = tariff_rate
                item.save()
                
                # Update all CostMaster records for this SKU (across all vendors)
                cost_masters = CostMaster.objects.filter(wwi_product_code=item.sku)
                for cm in cost_masters:
                    cm.tariff = tariff_rate
                    # Recalculate landed cost with new tariff
                    # Formula: (Price per kg * (1 + Tariff)) + Freight per kg
                    cm.calculate_landed_cost()
                    cm.save()
                
                print(f"Updated tariff for {item.sku}: {old_tariff} ({old_tariff * 100:.2f}%) -> {tariff_rate} ({tariff_rate * 100:.2f}%)", file=sys.stderr)
                logger.info(f"Updated tariff for {item.sku}: {old_tariff} ({old_tariff * 100:.2f}%) -> {tariff_rate} ({tariff_rate * 100:.2f}%)")
                updated_count += 1
            else:
                error_msg = f"Could not get tariff for {item.sku} (HTS: {item.hts_code}, Origin: {item.country_of_origin}) - Flexport API may not be configured correctly"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                logger.warning(error_msg)
                error_details.append(error_msg)
                error_count += 1
                
        except Exception as e:
            error_msg = f"Error updating tariff for {item.sku}: {str(e)}"
            print(f"EXCEPTION: {error_msg}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            logger.error(error_msg, exc_info=True)
            error_details.append(error_msg)
            error_count += 1
    
    print(f"Flexport tariff update complete: {updated_count} updated, {error_count} errors", file=sys.stderr)
    logger.info(f"Flexport tariff update complete: {updated_count} updated, {error_count} errors")
    return updated_count, error_count, error_details


if __name__ == '__main__':
    # Run the update
    updated, errors, details = update_tariffs()
    print(f"Updated {updated} items, {errors} errors")
    if details:
        print("Error details:")
        for detail in details:
            print(f"  - {detail}")
