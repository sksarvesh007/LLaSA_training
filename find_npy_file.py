import os
import numpy as np
def scan_for_npy_files(root_dir):
    npy_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.npy'):
                full_path = os.path.join(dirpath, filename)
                try:
                    # Try to load the file to verify it's a valid numpy array
                    arr = np.load(full_path, allow_pickle=True)
                    print(f"Found: {full_path}")
                    print(f"Shape: {arr.shape}, Type: {arr.dtype}")
                    npy_files.append(full_path)
                except Exception as e:
                    print(f"Error loading {full_path}: {e}")
    return npy_files

# Starting from current directory
root_dir = "."
print("Scanning for .npy files...")
npy_files = scan_for_npy_files(root_dir)

if npy_files:
    print("\nFound .npy files in these locations:")
    for file in npy_files:
        print(file)
else:
    print("\nNo .npy files found. You might need to generate VQ codes first.")