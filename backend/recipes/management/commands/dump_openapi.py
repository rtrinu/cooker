import json
from pathlib import Path

from django.core.management.base import BaseCommand

from recipes.api import api


class Command(BaseCommand):
    help = "Write the Ninja OpenAPI schema for frontend type generation."

    def add_arguments(self, parser):
        parser.add_argument(
            "output",
            nargs="?",
            default="frontend/openapi.json",
            help="Output path (default: frontend/openapi.json)",
        )

    def handle(self, *args, **options):
        path = Path(options["output"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(api.get_openapi_schema(), indent=2) + "\n")
        self.stdout.write(self.style.SUCCESS(f"Wrote OpenAPI schema to {path}"))
