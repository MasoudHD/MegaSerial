"""PyInstaller entry point for the MegaSerial standalone executable."""
import sys

from MegaSerial.app import main

if __name__ == "__main__":
    sys.exit(main())
