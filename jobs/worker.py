import os
import time
import config
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from file_converter import FileConverter
from modelos import File

# Configure SQLAlchemy to use the PostgreSQL database
engine = create_engine(config.POSTGRES_URI)
Session = sessionmaker(bind=engine)
session = Session()

# Path to your service account key file
service_account_key_path = './google-json/uniandes-grupo-10-9a07a80edaf8.json'

# Load the credentials from the JSON key file
credentials = service_account.Credentials.from_service_account_file(service_account_key_path)

# Set the credentials on the Pub/Sub subscriber client
subscriber = pubsub_v1.SubscriberClient(credentials=credentials)

subscription_path = subscriber.subscription_path(
    config.GOOGLE_PUBSUB_PROJECT_ID, config.GOOGLE_PUBSUB_SUBSCRIPTION_ID
)


def callback(message):
    payload = message.data.decode()
    file_id = message.attributes.get('file_id')
    filename = message.attributes.get('filename')
    new_format = message.attributes.get('new_format')

    print("Received message:")
    print("Payload:", payload)
    print("File ID:", file_id)
    print("Filename:", filename)
    print("New Format:", new_format)

    process_file(file_id, filename, new_format)

    message.ack()


def process_file(file_id, filename, new_format):
    UPLOAD_FOLDER = './uploads'
    PROCESS_FOLDER = './processed'
    filenameParts = filename.split('.')

    file = session.query(File).filter_by(id=file_id).first()
    log_file_path = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), 'log_conversion.txt')
    with open(log_file_path, 'a+') as file:
        file.write(
            '{} to {} - solicitud de conversion: {}\n'.format(filename, new_format, file.created_at))

    formats = {
        'zip': FileConverter.to_zip,
        'tar_gz': FileConverter.to_tar_gz,
        'tar_bz2': FileConverter.to_tar_bz2
    }

    attempt_counter = 0

    file_path = os.path.join(UPLOAD_FOLDER, secure_filename(filename))
    while not os.path.exists(file_path) or attempt_counter == 10:
        attempt_counter += 1
        print(f"File not found: {file_path}. Waiting 0.5 seconds...")
        time.sleep(0.5)
    print(f"File found: {file_path}")

    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    if new_format in formats.keys():
        print(f"calling {new_format}")
        func = formats[new_format]
        print(f"function: {func}")
        processed_filename = func(file_path, os.path.join(
            PROCESS_FOLDER, filenameParts[0]))
        print(f"original: {os.path.join(PROCESS_FOLDER, filename)}")
        print(f"destination: {processed_filename}")
        processed_filename_parts = processed_filename.split('/')
        file.processed_filename = processed_filename_parts[-1]
        file.state = 'PROCESSED'
        session.add(file)
        session.commit()
    else:
        print("invalid format")

if __name__ == "__main__":
    future = subscriber.subscribe(subscription_path, callback)

    # Keep the script running to continue listening for messages
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()