from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Category, Subcategory
import csv
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Load policy categories and subcategories from CSV file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-file',
            type=str,
            required=True,
            help='Path to the CSV file containing policy categories'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing categories before loading new ones'
        )

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        clear_existing = options['clear_existing']

        self.stdout.write(f"📁 Loading policy categories from: {csv_file_path}")

        # Clear existing data if requested
        if clear_existing:
            self.stdout.write("🗑️ Clearing existing categories and subcategories...")
            with transaction.atomic():
                Subcategory.objects.all().delete()
                Category.objects.all().delete()
            self.stdout.write(
                self.style.SUCCESS("✅ Existing data cleared")
            )

        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                # Read CSV content
                csv_reader = csv.DictReader(file)
                
                # Validate required columns
                required_columns = ['대범주', '소범주', '대범주 설명', '소범주 설명']
                if not all(col in csv_reader.fieldnames for col in required_columns):
                    self.stderr.write(
                        self.style.ERROR(
                            f"❌ CSV file must contain columns: {', '.join(required_columns)}"
                        )
                    )
                    return

                # Process categories
                categories_created = 0
                subcategories_created = 0
                category_cache = {}

                with transaction.atomic():
                    for row_num, row in enumerate(csv_reader, start=2):
                        try:
                            main_category = row['대범주'].strip()
                            sub_category = row['소범주'].strip()
                            main_description = row['대범주 설명'].strip()
                            sub_description = row['소범주 설명'].strip()

                            if not main_category or not sub_category:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"⚠️ Row {row_num}: Skipping empty category or subcategory"
                                    )
                                )
                                continue

                            # Get or create main category
                            if main_category not in category_cache:
                                category_obj, created = Category.objects.get_or_create(
                                    name=main_category,
                                    defaults={
                                        'description': main_description,
                                        'policy_area_code': f"CAT_{len(category_cache) + 1:03d}"
                                    }
                                )
                                category_cache[main_category] = category_obj
                                if created:
                                    categories_created += 1
                                    self.stdout.write(f"✨ Created category: {main_category}")
                            else:
                                category_obj = category_cache[main_category]

                            # Create subcategory
                            subcategory_obj, created = Subcategory.objects.get_or_create(
                                category=category_obj,
                                name=sub_category,
                                defaults={
                                    'description': sub_description,
                                    'policy_stance': self._determine_policy_stance(sub_category),
                                    'implementation_approach': sub_description
                                }
                            )

                            if created:
                                subcategories_created += 1
                                self.stdout.write(f"  ├── Created subcategory: {sub_category}")

                        except Exception as e:
                            self.stderr.write(
                                self.style.ERROR(
                                    f"❌ Error processing row {row_num}: {e}"
                                )
                            )
                            continue

                # Summary
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n🎉 Successfully loaded policy categories:"
                        f"\n   📂 Categories created: {categories_created}"
                        f"\n   📄 Subcategories created: {subcategories_created}"
                        f"\n   📊 Total categories: {Category.objects.count()}"
                        f"\n   📋 Total subcategories: {Subcategory.objects.count()}"
                    )
                )

                # Display category summary
                self.stdout.write("\n📊 Category Summary:")
                for category in Category.objects.all().order_by('name'):
                    subcat_count = category.subcategories.count()
                    self.stdout.write(f"  📂 {category.name}: {subcat_count} subcategories")

        except FileNotFoundError:
            self.stderr.write(
                self.style.ERROR(f"❌ CSV file not found: {csv_file_path}")
            )
        except csv.Error as e:
            self.stderr.write(
                self.style.ERROR(f"❌ CSV parsing error: {e}")
            )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"❌ Unexpected error: {e}")
            )

    def _determine_policy_stance(self, subcategory_name):
        """
        Determine policy stance based on subcategory name.
        This is a simple heuristic that can be improved.
        """
        progressive_keywords = ['확장', '증가', '강화', '도입', '지원', '보편']
        conservative_keywords = ['긴축', '감소', '완화', '인하', '축소', '선별']
        
        name_lower = subcategory_name.lower()
        
        if any(keyword in name_lower for keyword in progressive_keywords):
            return '진보'
        elif any(keyword in name_lower for keyword in conservative_keywords):
            return '보수'
        else:
            return '중도'
