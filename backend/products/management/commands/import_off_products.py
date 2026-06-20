import gzip
import json
import subprocess
import sys
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from products.models import Product

OFF_URL = "https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz"
GZIP_MAGIC = b"\x1f\x8b"

TARGET_COUNTRIES = frozenset({
    "en:united-states",
    "en:canada",
    "en:france",
    "en:united-kingdom",
    "en:germany",
    "en:spain",
    "en:italy",
    "en:netherlands",
    "en:belgium",
    "en:switzerland",
})


class Command(BaseCommand):
    help = "Import products from Open Food Facts JSONL export (US/Europe filter)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=None, metavar="N",
            help="Stop after N products are upserted (for test runs)",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and log without writing to the database",
        )
        parser.add_argument(
            "--skip-download", action="store_true",
            help="Use the existing local .gz file, skip download",
        )
        parser.add_argument(
            "--source", default=None, metavar="PATH",
            help="Local .gz file path to use instead of downloading",
        )
        parser.add_argument(
            "--batch-size", type=int, default=500, metavar="N",
            help="Products per DB upsert batch (default: 500)",
        )

    def handle(self, *args, **options):
        # backend/data/ — already gitignored
        data_dir = Path(__file__).resolve().parents[3] / "data"
        data_dir.mkdir(exist_ok=True)
        local_path = data_dir / "openfoodfacts-products.jsonl.gz"

        if options["source"]:
            local_path = Path(options["source"])
            if not local_path.exists():
                self.stderr.write(self.style.ERROR(f"Source file not found: {local_path}"))
                return
        elif not options["skip_download"]:
            self._download(OFF_URL, local_path)
        elif not local_path.exists():
            self.stderr.write(self.style.ERROR(
                f"No local file at {local_path}. Run without --skip-download first."
            ))
            return

        with open(local_path, "rb") as f:
            magic = f.read(2)
        if magic != GZIP_MAGIC:
            self.stderr.write(self.style.ERROR(
                f"{local_path} does not appear to be a valid gzip file (bad magic bytes)."
            ))
            return

        self._import(local_path, options)

    def _download(self, url, dest):
        self.stdout.write(f"Downloading {url}")
        self.stdout.write(f"  → {dest}")
        # curl handles SSL correctly on macOS/Linux without extra cert config,
        # and -L follows the 302 redirect that OFF's static host issues.
        result = subprocess.run(
            ["curl", "-L", "--progress-bar", "-o", str(dest), url],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl exited with code {result.returncode}")
        self.stdout.write(self.style.SUCCESS("Download complete."))

    def _import(self, path, options):
        limit = options["limit"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        counters = {
            "scanned": 0,
            "skipped_country": 0,
            "skipped_no_barcode": 0,
            "skipped_no_name": 0,
            "skipped_malformed": 0,
            "upserted": 0,
        }

        now = timezone.now()
        batch = []

        mode = "DRY RUN — no DB writes" if dry_run else f"batch_size={batch_size}"
        self.stdout.write(f"Processing {path} [{mode}] ...")

        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            for raw_line in self._safe_lines(f, counters):
                try:
                    record = json.loads(raw_line.strip())
                except json.JSONDecodeError:
                    counters["skipped_malformed"] += 1
                    continue

                countries = record.get("countries_tags") or []
                if isinstance(countries, str):
                    countries = [c.strip() for c in countries.split(",")]
                if not TARGET_COUNTRIES.intersection(countries):
                    counters["skipped_country"] += 1
                    continue

                barcode = (record.get("code") or "").strip().replace("\x00", "")
                if not barcode:
                    counters["skipped_no_barcode"] += 1
                    continue

                name = (
                    record.get("product_name_en")
                    or record.get("product_name")
                    or ""
                ).strip().replace("\x00", "")[:500]
                if not name:
                    counters["skipped_no_name"] += 1
                    continue

                brands_raw = (record.get("brands") or "").strip()
                brand = brands_raw.split(",")[0].strip().replace("\x00", "")[:255] if brands_raw else ""

                ingredients_text = (record.get("ingredients_text") or "").strip().replace("\x00", "")

                if limit and (counters["upserted"] + len(batch)) >= limit:
                    break

                batch.append(Product(
                    barcode=barcode[:50],
                    name=name,
                    brand=brand,
                    ingredients_text=ingredients_text,
                    off_id=barcode[:255],
                    created_at=now,
                    updated_at=now,
                ))

                if len(batch) >= batch_size:
                    self._flush(batch, dry_run, counters)
                    batch = []
                    sys.stdout.write(
                        f"\r  Upserted: {counters['upserted']:>7,}  "
                        f"Scanned: {counters['scanned']:>9,}  "
                        f"Skipped(country): {counters['skipped_country']:>7,}   "
                    )
                    sys.stdout.flush()

        if batch:
            self._flush(batch, dry_run, counters)

        sys.stdout.write("\n")
        self._print_summary(counters, dry_run)

    def _safe_lines(self, f, counters):
        """Yield lines from a gzip file, stopping cleanly on a truncated stream."""
        try:
            for line in f:
                counters["scanned"] += 1
                yield line
        except (EOFError, gzip.BadGzipFile, OSError):
            pass

    def _flush(self, batch, dry_run, counters):
        if dry_run:
            counters["upserted"] += len(batch)
            return
        # OFF sometimes has duplicate barcodes; keep last occurrence so bulk_create
        # doesn't attempt to UPDATE the same row twice in one statement.
        deduped = list({p.barcode: p for p in batch}.values())
        Product.objects.bulk_create(
            deduped,
            update_conflicts=True,
            unique_fields=["barcode"],
            update_fields=["name", "brand", "ingredients_text", "off_id", "updated_at"],
        )
        counters["upserted"] += len(deduped)

    def _print_summary(self, counters, dry_run):
        label = "DRY RUN complete" if dry_run else "Import complete"
        self.stdout.write(self.style.SUCCESS(f"\n{label}:"))
        self.stdout.write(f"  Lines scanned:          {counters['scanned']:>10,}")
        self.stdout.write(f"  Skipped (country):      {counters['skipped_country']:>10,}")
        self.stdout.write(f"  Skipped (no barcode):   {counters['skipped_no_barcode']:>10,}")
        self.stdout.write(f"  Skipped (no name):      {counters['skipped_no_name']:>10,}")
        self.stdout.write(f"  Skipped (malformed):    {counters['skipped_malformed']:>10,}")
        self.stdout.write(f"  Upserted:               {counters['upserted']:>10,}")
