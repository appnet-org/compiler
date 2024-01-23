import os
from pathlib import Path

if __name__ == "__main__":
    element_dir = Path(__file__).parent
    for subdir, dirs, files in os.walk(element_dir):
        for file in files:
            file_path = os.path.join(subdir, file)
            adn_content = open(file_path).read()
            if "strong" in file_path:
                assert "@consistency" in adn_content, file_path
            if "weak" in file_path:
                assert "@" not in adn_content, file_path
