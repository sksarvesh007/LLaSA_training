import torch
print(torch.cuda.is_available())  # Should return True if GPU is detected
print(torch.cuda.device_count())  # Number of GPUs
