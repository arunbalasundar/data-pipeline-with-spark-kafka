from __future__ import annotations

import pendulum

from airflow.models.dag import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

# Define default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'start_date': pendulum.datetime(2023, 1, 1, tz="UTC"),
    'retries': 1,
    'retry_delay': pendulum.duration(minutes=5),
}

# Define the DAG
with DAG(
    dag_id='spark_kafka_consumer_pipeline',
    default_args=default_args,
    description='A DAG to consume COVID-19 data from Kafka, aggregate it with Spark Streaming, and store it in MySQL.',
    schedule=None, # This DAG will be triggered manually for now. Change to '@daily' or a cron expression for automation.
    tags=['spark', 'kafka', 'mysql', 'covid'],
    catchup=False,
) as dag:
    # Task to submit the Spark Structured Streaming job
    submit_spark_consumer_to_kafka = SparkSubmitOperator(
        task_id='submit_spark_consumer_to_kafka',
        application='/opt/spark/app/spark_consumer_kafka.py', # Path to your Spark application script within the Spark container
        conn_id='spark_default', # This connection ID must be configured in Airflow UI
        packages='org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.0,mysql:mysql-connector-java:8.0.28', # Spark-Kafka integration, MySQL JDBC driver
        # application_args provide arguments to the spark_kafka_consumer.py script
        # 1. Kafka bootstrap servers for the Spark consumer (internal Docker network name and port)
        # 2. Kafka topic to subscribe to
        application_args=["kafka:9092", "covid_data"], # Spark connects to Kafka's INTERNAL listener via Docker network
        total_executor_cores=2,
        executor_cores=1,
        executor_memory='2g',
        driver_memory='1g',
        num_executors=2,
        conf={
            "spark.sql.streaming.checkpointLocation": "/tmp/spark-checkpoint", # Important for stateful streaming
            "spark.sql.shuffle.partitions": "200", # Adjust based on data volume and cluster size
            "spark.driver.extraJavaOptions": "-Dlog4j.configuration=file:/opt/spark/conf/log4j2.properties",
            "spark.executor.extraJavaOptions": "-Dlog4j.configuration=file:/opt/spark/conf/log4j2.properties"
        },
    )

