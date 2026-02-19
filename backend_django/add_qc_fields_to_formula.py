"""
Script to add QC parameter fields to Formula model
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wwi_erp.settings')
django.setup()

from django.db import connection

def add_qc_fields_to_formula():
    """Add QC parameter fields to Formula table"""
    with connection.cursor() as cursor:
        try:
            # Check if columns already exist
            cursor.execute("""
                SELECT COUNT(*) FROM pragma_table_info('erp_core_formula') 
                WHERE name IN ('qc_parameter_name', 'qc_spec_min', 'qc_spec_max')
            """)
            existing = cursor.fetchone()[0]
            
            if existing == 3:
                print("QC fields already exist in Formula table")
                return
            
            # Add qc_parameter_name column
            cursor.execute("""
                ALTER TABLE erp_core_formula 
                ADD COLUMN qc_parameter_name VARCHAR(255) NULL
            """)
            print("Added qc_parameter_name column")
            
            # Add qc_spec_min column
            cursor.execute("""
                ALTER TABLE erp_core_formula 
                ADD COLUMN qc_spec_min REAL NULL
            """)
            print("Added qc_spec_min column")
            
            # Add qc_spec_max column
            cursor.execute("""
                ALTER TABLE erp_core_formula 
                ADD COLUMN qc_spec_max REAL NULL
            """)
            print("Added qc_spec_max column")
            
            print("Successfully added QC fields to Formula table")
            
        except Exception as e:
            if 'duplicate column name' in str(e).lower():
                print(f"Some columns may already exist: {e}")
            else:
                print(f"Error adding QC fields: {e}")
                raise

if __name__ == '__main__':
    add_qc_fields_to_formula()
