"""
Main module for the memory system. Allows running the memory patch directly.
"""

from .memory_patch import patch_main_file

if __name__ == "__main__":
    print("Applying memory system patch to main.py...")
    patch_main_file()
    print("Done. You can now run the SimuVerse backend with the memory system enabled.")