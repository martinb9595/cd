import os

import openai

import time

import logging

import json

import datetime

from sqlalchemy import create_engine, exc

from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import sessionmaker

from functools import lru_cache

from concurrent.futures import ThreadPoolExecutor, as_completed

from threading import Lock

import re



# Constants

MAX_TOKENS_PER_MINUTE = 30000

OPTIMIZED_FILES_MAX_LINES = None  # Set to None for unlimited lines



# Set up logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



# Set the OpenAI API key directly

openai.api_key = 'your_api_key'  # Replace with your actual API key



# Database configuration parameters

DB_CONNECTION = 'mysql+pymysql'

DB_HOST = 'YOUR_DB_HOST'

DB_PORT = '3306'

DB_DATABASE = 'YOUR_DB_NAME'

DB_USERNAME = 'YOUR_DB_USERNAME'

DB_PASSWORD = 'YOUR_DB_PASSWORD'



# SQLAlchemy setup

DATABASE_URL = f"{DB_CONNECTION}://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

Base = declarative_base()

SessionLocal = sessionmaker(bind=engine)



# Output paths

output_directory = r"D:\output"

optimized_files_list_path = os.path.join(output_directory, "optimized.txt")

optimization_status_file_path = os.path.join(output_directory, "optimization_status.json")

optimize_output_path = os.path.join(output_directory, "optimize.json")



token_lock = Lock()

current_minute = datetime.datetime.now().minute

tokens_used = 0



def check_write_permissions(directory):

    test_file_path = os.path.join(directory, "test_permission.txt")

    try:

        with open(test_file_path, 'w') as test_file:

            test_file.write("test")

        os.remove(test_file_path)

        logging.info(f"Write permission check passed for directory: {directory}")

        return True

    except IOError as e:

        logging.error(f"Write permission check failed for directory: {directory}. Error: {e}")

        return False



# Ensure output directory exists and has write permissions

os.makedirs(output_directory, exist_ok=True)

if not check_write_permissions(output_directory):

    logging.error("Exiting due to insufficient directory permissions.")

    exit(1)



@lru_cache(maxsize=128)

def get_chat_response_from_openai(prompt, model="gpt-4o-mini"):  # Model switched here

    global tokens_used, current_minute

    while True:

        try:

            # Check and reset token usage every new minute

            with token_lock:

                now = datetime.datetime.now()

                if now.minute != current_minute:

                    current_minute = now.minute

                    tokens_used = 0



            response = openai.ChatCompletion.create(

                model=model,

                messages=[

                    {"role": "user", "content": prompt}

                ],

            )



            used_tokens = response.usage['total_tokens']

            with token_lock:

                tokens_used += used_tokens



            return response.choices[0].message['content']

        except openai.error.RateLimitError as e:

            logging.warning(f"Rate limit error: {e}")

            wait_time = float(re.search(r"Please try again in (\d+(?:\.\d+)?)s", str(e)).group(1))

            logging.info(f"Waiting for {wait_time:.2f} seconds before retrying.")

            time.sleep(wait_time * 1.1)  # Adding a buffer to ensure the wait time is sufficient

        except openai.error.OpenAIError as e:

            logging.error(f"OpenAI API error: {e}. Retrying in 10 seconds.")

            time.sleep(10)



def optimize_laravel_code(lara_code):

    prompt = f"Optimize the following Laravel PHP code:\n\n{lara_code}"

    while True:

        try:

            return get_chat_response_from_openai(prompt)

        except Exception as e:

            logging.warning(f"Error optimizing code: {e}. Retrying...")

            time.sleep(5)



def load_optimized_files():

    if os.path.exists(optimized_files_list_path):

        with open(optimized_files_list_path, 'r', encoding='utf-8') as f:

            return set(f.read().splitlines())

    return set()



def save_optimized_files(optimized_files):

    # If unlimited, just save the files without max lines limit

    with open(optimized_files_list_path, 'w', encoding='utf-8') as f:

        f.write('\n'.join(optimized_files))

    logging.info(f"Optimized files list saved to {optimized_files_list_path}, current lines: {len(optimized_files)}.")



def load_optimization_status():

    if os.path.exists(optimization_status_file_path):

        with open(optimization_status_file_path, 'r', encoding='utf-8') as f:

            return json.load(f)

    return {}



def save_optimization_status(optimization_status):

    with open(optimization_status_file_path, 'w', encoding='utf-8') as f:

        json.dump(optimization_status, f, ensure_ascii=False, indent=4)

    logging.info(f"Optimization status saved to {optimization_status_file_path}.")



def save_optimization_output(output_data):

    with open(optimize_output_path, 'w', encoding='utf-8') as f:

        json.dump(output_data, f, ensure_ascii=False, indent=4)

    logging.info(f"Optimization output saved to {optimize_output_path}.")



def estimate_time_remaining(start_time, processed_files, total_files):

    if processed_files > 0:

        average_time_per_file = (time.time() - start_time) / processed_files

        remaining_files = total_files - processed_files

        estimated_time_left = datetime.timedelta(seconds=remaining_files * average_time_per_file)

        logging.info(f"Estimated time remaining: {estimated_time_left}")

    else:

        logging.info("Estimating time remaining: Not enough files processed yet")



def process_files(file_paths, optimized_files, optimization_status, optimization_results):

    for file_path in file_paths:

        if file_path in optimized_files:

            logging.info(f"Skipping already optimized file: {file_path}")

            continue



        logging.info(f"Optimizing file: {file_path}")

        try:

            with open(file_path, 'r', encoding='utf-8') as file:

                original_code = file.read()



            # Split code into chunks of 30,000 characters

            chunks = [original_code[i:i + 30000] for i in range(0, len(original_code), 30000)]



            optimized_code = ""

            for chunk in chunks:

                optimized = False

                while not optimized:

                    try:

                        optimized_code_chunk = optimize_laravel_code(chunk)

                        if optimized_code_chunk is not None:

                            optimized_code += optimized_code_chunk

                            optimized = True

                        else:

                            logging.error(f"Optimization failed for a chunk of file: {file_path}. Retrying...")

                    except Exception as e:

                        logging.error(f"Chunk optimization error: {e}. Retrying...")

                        time.sleep(5)



            if optimized_code:

                with open(file_path, 'w', encoding='utf-8') as file:

                    file.write(optimized_code)



                logging.info(f"Successfully optimized: {file_path}")

                optimized_files.add(file_path)

                optimization_status[file_path] = {"status": "completed", "reason": None}

                optimization_results[file_path] = optimized_code



        except Exception as e:

            logging.error(f"Error processing file {file_path}: {e}")

            optimization_status[file_path] = {"status": "failed", "reason": str(e)}



def optimize_files_in_directory(directory_path):

    optimized_files = load_optimized_files()

    optimization_status = load_optimization_status()



    all_php_files = []

    for dirpath, _, filenames in os.walk(directory_path):

        for filename in filenames:

            if filename.endswith('.php'):

                all_php_files.append(os.path.join(dirpath, filename))



    total_files = len(all_php_files)

    logging.info(f"Total PHP files to optimize: {total_files}")



    optimization_results = {}

    start_time = time.time()



    chunk_size = 10

    file_chunks = [all_php_files[i:i + chunk_size] for i in range(0, total_files, chunk_size)]



    with ThreadPoolExecutor(max_workers=10) as executor:

        futures = {executor.submit(process_files, chunk, optimized_files, optimization_status, optimization_results): chunk for chunk in file_chunks}



        for future in as_completed(futures):

            try:

                future.result()

            except Exception as e:

                logging.error(f"An error occurred during optimization: {e}")



            save_optimized_files(optimized_files)

            save_optimization_status(optimization_status)

            save_optimization_output(optimization_results)



            estimate_time_remaining(start_time, len(optimized_files), total_files)



    logging.info(f"Files optimized: {len(optimized_files)}. Total files left for optimization: {total_files - len(optimized_files)}.")



def main():

    project_path = r"D:/nexgen.to"

    optimize_files_in_directory(project_path)



if __name__ == "__main__":

    main()