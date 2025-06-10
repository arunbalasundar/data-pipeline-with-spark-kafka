# data-pipeline-with-spark-kafka
This repository provides a robust and scalable data pipeline designed to ingest, process, and analyze real-time COVID-19 related data streams. Built with Apache Kafka for data ingestion, Apache Spark for distributed processing, and Apache Airflow for workflow orchestration, the entire stack is containerized using Docker and Docker Compose for easy setup and deployment.

## Overview
* **Apache Kafka:** Serves as a high-throughput, fault-tolerant message broker for ingesting raw COVID-19 data.
* **Apache Spark:** A streaming application that continuously consumes data from Kafka, performs transformations (e.g., windowed aggregations), and outputs the results.
* **Apache Airflow:** Orchestrates the entire workflow, specifically responsible for submitting the Spark streaming job to the Spark cluster.
* **Docker & Docker Compose:** Containerize all services (Kafka, Zookeeper, Spark Master, Spark Worker, Airflow Webserver, Airflow Scheduler, Airflow Worker) for consistent and isolated local development/testing environments.

## Project Structure

```data-pipeline-with-spark-kafka/
├── Dockerfile.airflow              # Airflow environment with Spark client.
├── Dockerfile.spark_vanilla        # Builds Spark cluster images
├── airflow_home/
│   ├── dags/
│   │   └── spark_dag.py            # Airflow DAG: Orchestrates the Spark consumer job submission.
│   └── scripts/
│       ├── kafka_consumer_spark.py # PySpark application: Reads from Kafka, processes data.
│       └── kafka_producer.py       # Python script: Produces sample COVID-19 data to Kafka.
├── data/                           # Directory for source data files
│   └── sample_covid.csv            # Sample CSV data used by kafka_producer.py
├── docker-compose.yml              # Defines and links all Docker services (Kafka, Spark, Airflow components)
├── .gitignore                      # Specifies intentionally untracked files and directories.
└── README.md                       # This documentation file.
```
## Prerequisites
**Docker Desktop:** This includes Docker Engine and Docker Compose, essential for spinning up all the services.
 * [Download Docker Desktop](https://www.docker.com/products/docker-desktop)

## Getting Started
### Clone the Repository
``` git clone https://github.com/arunbalasundar/data-pipeline-with-spark-kafka.git```
```cd data-pipeline-with-spark-kafka```

### Prepare Sample Data
The kafka_producer.py script requires a sample_covid.csv file. You must place your sample_covid.csv file in a data folder at the root of your cloned repository.

```mkdir -p data```
Copy your sample_covid.csv into the new 'data' folder
```cp /path/to/your/sample_covid.csv data/sample_covid.csv```
(Ensure sample_covid.csv contains appropriate columns like 'date', 'location', 'new_cases', 'total_cases' as expected by kafka_producer.py.)

### Build docker images and Start services
Build the custom Docker images and launch all the defined services (Kafka, Zookeeper, Spark Master, Spark Worker, Airflow components) in detached mode.

```docker-compose build```
```docker-compose up -d```

## Access Airflow UI: 
Open your web browser and navigate to http://localhost:8080.

### Create Spark Connection:
* Go to Admin > Connections.
* Click the + button to create a new connection.
* Conn Id: spark_default1 (This must exactly match the connection ID used in your spark_dag.py)
* Conn Type: Spark
* Master URI: spark://spark-master:7077 (This allows Airflow to connect to your Spark Master container within the Docker network)

### kafka topic and data creation
The pipeline relies on a Kafka topic named covid_data. Your kafka_producer.py script sends data to this topic.

Find an Airflow Container ID: (e.g., airflow_worker or airflow_scheduler)
```docker ps | grep airflow_worker # Or 'airflow_scheduler'```
Exec into the container:
```docker exec -it <airflow_container_id> bash```

Run the producer script:
```cd /opt/airflow/scripts/```
```python3 kafka_producer.py kafka:9092```

# Enable and Trigger Airflow DAG
Run ```spark_kafka_consumer_pipeline``` DAG
