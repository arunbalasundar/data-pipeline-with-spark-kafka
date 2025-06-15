import csv
import json
import time
import requests
import io
import os
from kafka import KafkaProducer
from kafka.errors import KafkaTimeoutError # Corrected import for KafkaTimeoutError

# --- Kafka Configuration ---
# This must match the external host port exposed by your Kafka Docker container (from docker-compose.yml)
KAFKA_BOOTSTRAP_SERVERS = 'localhost:29092' # This is the port exposed on your Mac
KAFKA_TOPIC = 'covid_data'

# --- Public API Configuration (Our World in Data) ---
OWID_COVID_DATA_URL = "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv"

# --- Producer Settings ---
SEND_DELAY_SECONDS = 0.01

def get_covid_data_from_api(url):
    """
    Fetches the COVID-19 data from the specified URL.
    Returns the content as a string.
    """
    print(f"Fetching data from: {url}")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        print("Successfully fetched data.")
        return response.content.decode('utf-8-sig')
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from API: {e}")
        return None

def run_producer():
    """
    Connects to Kafka, fetches data from the OWID API, and sends it to the topic.
    """
    # Initialize Kafka Producer
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS],
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        client_id='covid_producer_v2', # Added client_id
        retries=10, # Increased retries
        linger_ms=100,
        request_timeout_ms=240000, # Increased timeout to 4 minutes (240 seconds)
        api_version=(2, 9, 0),    # Bumped API version slightly
        acks='all',               # Wait for all in-sync replicas to acknowledge
        delivery_timeout_ms=245000, # Must be > (linger_ms + request_timeout_ms)
        connections_max_idle_ms=300000 # Keep connections open for 5 minutes
    )
    print(f"Producer attempting to connect to: {KAFKA_BOOTSTRAP_SERVERS}")

    csv_data_string = get_covid_data_from_api(OWID_COVID_DATA_URL)
    if csv_data_string is None:
        print("Failed to get data from API. Exiting producer.")
        producer.close()
        return

    csv_file = io.StringIO(csv_data_string)
    reader = csv.DictReader(csv_file)

    sent_count = 0

    try:
        for row in reader:
            # Basic validation for essential fields before processing
            if not all(k in row and row[k] is not None for k in ['date', 'location', 'new_cases', 'total_cases']):
                # print(f"Skipping row due to missing essential data: {row}")
                continue

            try:
                # Convert new_cases and total_cases to integers, handling empty strings/None
                # Default to 0 if conversion fails or value is missing
                new_cases = int(float(row['new_cases'])) if row.get('new_cases') and row['new_cases'].strip() else 0
                total_cases = int(float(row['total_cases'])) if row.get('total_cases') and row['total_cases'].strip() else 0

                message = {
                    "date": row['date'],
                    "location": row['location'],
                    "new_cases": new_cases,
                    "total_cases": total_cases
                }

                # Send the message to Kafka and wait for acknowledgment
                future = producer.send(KAFKA_TOPIC, value=message)
                record_metadata = future.get(timeout=producer.config['request_timeout_ms'] / 1000) # Use producer's request_timeout_ms

                sent_count += 1
                if sent_count % 100 == 0: # Print every 100 records for more frequent updates
                    print(f"Sent {sent_count} records so far. Last sent to topic {record_metadata.topic} partition {record_metadata.partition} offset {record_metadata.offset}")

                time.sleep(SEND_DELAY_SECONDS)

            except ValueError as ve:
                print(f"Skipping row due to data type conversion error: {ve}, Row: {row}")
            except KafkaTimeoutError as ktoe:
                print(f"KafkaTimeoutError: Failed to send message after timeout: {ktoe}, Row: {row}")
                # For troubleshooting, you might want to break here to inspect more closely
            except Exception as e:
                print(f"General Error sending message: {e}, Row: {row}")

    except Exception as e:
        print(f"An unexpected error occurred during data processing loop: {e}")
    finally:
        # Ensure any buffered messages are sent before closing
        producer.flush()
        producer.close()
        print(f"Producer finished. Total records sent: {sent_count}")

if __name__ == "__main__":
    run_producer()
