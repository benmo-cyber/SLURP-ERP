from django.core.management.base import BaseCommand

from erp_core.sample_xml_import import find_xml_files, get_private_sample_data_dir, import_all_private_xml


class Command(BaseCommand):
    help = "Import all *.xml files from data/private_sample_data/ (see data/sample_import_template.xml)"

    def handle(self, *args, **options):
        d = get_private_sample_data_dir()
        self.stdout.write(f"Looking in: {d}")
        files = find_xml_files()
        if not files:
            self.stdout.write(self.style.WARNING("No .xml files found. Copy data/sample_import_template.xml into that folder."))
            return
        for f in files:
            self.stdout.write(f"  Found: {f.name}")
        result = import_all_private_xml()
        self.stdout.write(self.style.SUCCESS(str(result)))
