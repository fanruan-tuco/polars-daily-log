"""Entry point: python -m auto_daily_log"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Auto Daily Log")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--port", type=int, help="Override server port")
    args = parser.parse_args()
    print(f"Auto Daily Log v0.1.0 - config: {args.config}")


if __name__ == "__main__":
    main()
