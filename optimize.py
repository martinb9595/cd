import os
import openai
import time
import logging
import json
import datetime
from sqlalchemy import create_engine, Column, String, Enum, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import re

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set the OpenAI API key directly
openai.api_key = 'replace_api_key'  # Replace with your actual API key

# Database configuration parameters
DB_CONNECTION = 'mysql+pymysql'
DB_HOST = 'ip'
DB_PORT = '3306'
DB_DATABASE = 'db'
DB_USERNAME = 'db'
DB_PASSWORD = 'db'

# SQLAlchemy setup
DATABASE_URL = f"{DB_CONNECTION}://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# Define a model to track optimized files in the database
class OptimizedFile(Base):
    __tablename__ = 'optimized_files'
    filename = Column(String, primary_key=True)
    status = Column(Enum('completed', 'failed'))
    reason = Column(String)

# Create the table if it doesn't exist
Base.metadata.create_all(engine)

# Output paths
output_directory = r"D:\output"
optimized_files_list_path = os.path.join(output_directory, "optimized.txt")
optimize_output_path = os.path.join(output_directory, "optimize.json")

token_lock = Lock()
current_minute = datetime.datetime.now().minute

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
def get_chat_response_from_openai(prompt, model="gpt-4o-mini"):
    while True:
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message['content']
        except openai.error.RateLimitError as e:
            logging.warning(f"Rate limit error: {e}")
            wait_time = float(re.search(r"Please try again in (\d+(?:\.\d+)?)s", str(e)).group(1))
            logging.info(f"Waiting for {wait_time:.2f} seconds before retrying.")
            time.sleep(wait_time * 1.1)
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

def load_optimized_files_from_db(session):
    return {file.filename for file in session.query(OptimizedFile).all()}

def save_optimized_file_to_db(session, filename, status, reason=None):
    optimized_file = OptimizedFile(filename=filename, status=status, reason=reason)
    session.merge(optimized_file)  # Merge instead of add for upsert behavior
    session.commit()
    
def process_files(file_paths):
    session = SessionLocal()  # Create a session for each chunk
    optimized_files = load_optimized_files_from_db(session)

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
                        if optimized_code_chunk:
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

                # Save the optimization status to the database
                save_optimized_file_to_db(session, file_path, 'completed')

        except Exception as e:
            logging.error(f"Error processing file {file_path}: {e}")
            # Save the failure status to the database
            save_optimized_file_to_db(session, file_path, 'failed', str(e))

    session.close()  # Close the session at the end of processing

def optimize_files_in_directory(directory_path):
    all_php_files = []
    for dirpath, _, filenames in os.walk(directory_path):
        for filename in filenames:
            if filename.endswith('.php'):
                all_php_files.append(os.path.join(dirpath, filename))

    total_files = len(all_php_files)
    logging.info(f"Total PHP files to optimize: {total_files}")

    chunk_size = 10
    file_chunks = [all_php_files[i:i + chunk_size] for i in range(0, total_files, chunk_size)]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_files, chunk): chunk for chunk in file_chunks}

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"An error occurred during optimization: {e}")

def main():
    project_path = r"D:/nexgen.to"  # Adjust path as needed
    optimize_files_in_directory(project_path)

if __name__ == "__main__":
    main()