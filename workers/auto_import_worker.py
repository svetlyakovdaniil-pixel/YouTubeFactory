import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.media_importer import MediaImporter, print_results


def main():
    print("===== Auto Import Worker started =====", flush=True)

    importer = MediaImporter(stable_seconds=8)

    while True:
        results = importer.import_all()
        print_results(results)
        time.sleep(10)


if __name__ == "__main__":
    main()
