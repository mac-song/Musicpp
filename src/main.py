import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.presentation.main_window import main

if __name__ == "__main__":
    main()
