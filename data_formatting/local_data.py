#I have dataset ID from huggingface , save it locally in data folder 

from datasets import load_dataset

# Login using e.g. `huggingface-cli login` to access this dataset
ds = load_dataset("Mikhil-jivus/testHindiVoice")