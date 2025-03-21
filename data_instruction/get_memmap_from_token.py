import os
import numpy as np
import torch
from transformers import AutoTokenizer
from tqdm import tqdm
import multiprocessing
from datasets import load_from_disk

def init_worker(transcriptions_, audio_arrays_, tokenizer_, max_seq_len_, base_num_):
    global transcriptions, audio_arrays, tokenizer, max_seq_len, base_num
    transcriptions = transcriptions_
    audio_arrays = audio_arrays_
    tokenizer = tokenizer_
    max_seq_len = max_seq_len_
    base_num = base_num_

def process_audio_id(audio_id):
    transcript = transcriptions.get(audio_id)
    if transcript is None:
        return None   

    # Get the audio data directly from chunked_audio_filepath
    audio_data = audio_arrays.get(audio_id)
    if audio_data is None:
        return None
 
    # Convert audio data to tokens (using the array directly)
    codes = base_num + torch.tensor(audio_data, dtype=torch.long)
 
    text_with_special = f"<|TEXT_UNDERSTANDING_START|>{transcript}<|TEXT_UNDERSTANDING_END|>"
    encoded_text = tokenizer.encode_plus(
        text_with_special,
        add_special_tokens=False,
        return_tensors='np'
    )
    text_input_ids = encoded_text['input_ids'].squeeze(0)  # (text_len,)
 
    speech_gen_start_id = tokenizer.convert_tokens_to_ids('<|SPEECH_GENERATION_START|>')
    speech_gen_end_id = tokenizer.convert_tokens_to_ids('<|SPEECH_GENERATION_END|>')
    code_input_ids = np.array(
        [speech_gen_start_id] +
        codes.tolist() +
        [speech_gen_end_id],
        dtype=np.int32
    )

    total_input_ids = np.concatenate([text_input_ids, code_input_ids])

    if len(total_input_ids) > max_seq_len:
        total_input_ids = total_input_ids[:max_seq_len]
    else:
        padding_length = max_seq_len - len(total_input_ids)
        total_input_ids = np.pad(
            total_input_ids,
            (0, padding_length),
            'constant',
            constant_values=tokenizer.pad_token_id
        )

    return total_input_ids.astype(np.int32)

def process_data(dataset_dict, output_dir_tts, num_processes=4):
    max_seq_len = 2048
 
    tokenizer = AutoTokenizer.from_pretrained(
        'meta-llama/Llama-2-7b-hf',
        model_max_length=2048,
        padding_side="right",
        use_fast=True,
        trust_remote_code=True
    )
 
    tokenizer.pad_token = tokenizer.eos_token

    special_tokens = [
        '<|TEXT_GENERATION_START|>', '<|TEXT_GENERATION_END|>',
        '<|TEXT_UNDERSTANDING_START|>', '<|TEXT_UNDERSTANDING_END|>',
        '<|SPEECH_GENERATION_START|>', '<|SPEECH_GENERATION_END|>',
        '<|SPEECH_UNDERSTANDING_START|>', '<|SPEECH_UNDERSTANDING_END|>'
    ]
    tokenizer.add_tokens(special_tokens)
    special_token_ids = tokenizer.convert_tokens_to_ids(special_tokens)
 
    base_num = len(tokenizer)

    # Get audio IDs and data from dataset
    train_dataset = dataset_dict['train']
    audio_ids = [os.path.splitext(os.path.basename(filepath))[0] 
                 for filepath in train_dataset['audio_filepath']]
    
    # Create dictionaries from dataset
    transcriptions = {
        os.path.splitext(os.path.basename(filepath))[0]: text 
        for filepath, text in zip(train_dataset['audio_filepath'], train_dataset['text'])
    }
    
    # Modified: Access the array from the dictionary structure
    audio_arrays = {
        os.path.splitext(os.path.basename(filepath))[0]: audio_data['array']
        for filepath, audio_data in zip(train_dataset['audio_filepath'], 
                                      train_dataset['chunked_audio_filepath'])
    }

    # Split into train/val (90/10 split since we have 100 samples)
    np.random.shuffle(audio_ids)
    val_audio_ids = audio_ids[-10:]  # 10% for validation
    train_audio_ids = audio_ids[:-10]

    num_processes = min(num_processes, multiprocessing.cpu_count())

    with multiprocessing.Pool(
        num_processes,
        initializer=init_worker,
        initargs=(transcriptions, audio_arrays, tokenizer, max_seq_len, base_num)
    ) as pool:
        results = list(tqdm(
            pool.imap_unordered(process_audio_id, train_audio_ids),
            total=len(train_audio_ids),
            desc="data processing"
        ))
    train_tts_input_ids_list = [res for res in results if res is not None]

    init_worker(transcriptions, audio_arrays, tokenizer, max_seq_len, base_num)
    val_tts_input_ids_list = []
    for audio_id in tqdm(val_audio_ids, desc="valid data processing"):
        res = process_audio_id(audio_id)
        if res is not None:
            val_tts_input_ids_list.append(res)
 
    if not (train_tts_input_ids_list or val_tts_input_ids_list):
        print("bug ")
        return

    all_ids = train_tts_input_ids_list + val_tts_input_ids_list
    max_total_token_len = max(len(ids) for ids in all_ids)
 
    os.makedirs(output_dir_tts, exist_ok=True)

    train_tts_input_ids_array = np.array(train_tts_input_ids_list)
    val_tts_input_ids_array = np.array(val_tts_input_ids_list)

    train_tts_memmap_path = os.path.join(output_dir_tts, 'train_input_ids.memmap')
    train_tts_memmap = np.memmap(
        train_tts_memmap_path, dtype='int32', mode='w+', shape=train_tts_input_ids_array.shape
    )
    train_tts_memmap[:] = train_tts_input_ids_array[:]
    del train_tts_memmap   

    val_tts_memmap_path = os.path.join(output_dir_tts, 'val_input_ids.memmap')
    val_tts_memmap = np.memmap(
        val_tts_memmap_path, dtype='int32', mode='w+', shape=val_tts_input_ids_array.shape
    )
    val_tts_memmap[:] = val_tts_input_ids_array[:]
    del val_tts_memmap   

    np.save(os.path.join(output_dir_tts, 'train_input_ids_shape.npy'), train_tts_input_ids_array.shape)
    np.save(os.path.join(output_dir_tts, 'val_input_ids_shape.npy'), val_tts_input_ids_array.shape)

    print(f" TTS memmap  saved ! {output_dir_tts}")

if __name__ == "__main__":
    # Load the dataset
    dataset_dict = load_from_disk("dataset")
    
    # Set output path
    output_dir_tts = 'generated_memmap'   # Update this to where you want to save the memmap files
    
    num_processes = 8

    process_data(
        dataset_dict,
        output_dir_tts,
        num_processes=num_processes
    )
