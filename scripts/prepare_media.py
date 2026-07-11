import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path("/opt/youtubefactory")
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.media_pipeline import prepare_all_channels, prepare_channel_loop_videos, ensure_stream_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    ensure_stream_profile()

    if args.channel:
        results = prepare_channel_loop_videos(args.channel, force=args.force)
    else:
        results = prepare_all_channels(force=args.force)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
