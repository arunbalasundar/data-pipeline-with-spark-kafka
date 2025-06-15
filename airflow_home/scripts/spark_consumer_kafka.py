import sys
from pyspark.sql import SparkSession
# ADDED current_timestamp here
from pyspark.sql.functions import from_json, col, window, sum, avg, max, to_timestamp, lit, current_timestamp 
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType, DecimalType, LongType

# Define Kafka and MySQL connection details from command line arguments
kafka_bootstrap_servers = sys.argv[1]
kafka_topic = sys.argv[2]

# MySQL connection details
mysql_jdbc_url = "jdbc:mysql://mysql:3306/airflow" # Using Docker service name 'mysql'
mysql_table = "covid_aggregates"
mysql_user = "airflow"
mysql_password = "airflow"

# Initialize Spark Session
spark = SparkSession.builder \
    .appName("CovidDataStreamProcessor") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.0,mysql:mysql-connector-java:8.0.28") \
    .config("spark.sql.adaptive.enabled", "true") \
    .master("spark://spark-master:7077") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN") # Set Spark logging level to WARN

# --- Read Static Countries Data ---
countries_df = spark.read \
    .format("jdbc") \
    .option("url", mysql_jdbc_url) \
    .option("dbtable", "countries") \
    .option("user", mysql_user) \
    .option("password", mysql_password) \
    .option("driver", "com.mysql.cj.jdbc.Driver") \
    .load()

countries_df = countries_df.select(
    col("name").alias("country_name"),
    col("population").cast(LongType()).alias("country_population"),
    col("continent").alias("country_continent")
)
countries_df.cache() # Cache this DataFrame as it will be reused for every micro-batch
print("Successfully loaded countries data.")
countries_df.show(5) # For debugging/verification

# Define the schema for the incoming Kafka messages (JSON payload)
schema = StructType([
    StructField("date", StringType(), True),
    StructField("location", StringType(), True),
    StructField("new_cases", IntegerType(), True),
    StructField("total_cases", IntegerType(), True)
])

# Read data from Kafka using Spark Structured Streaming
kafka_df = spark \
    .readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", kafka_bootstrap_servers) \
    .option("subscribe", kafka_topic) \
    .option("startingOffsets", "earliest") \
    .option("failOnDataLoss", "false") \
    .load()

# Parse the Kafka message value (which is JSON)
parsed_df = kafka_df.selectExpr("CAST(value AS STRING) as json_value", "timestamp") \
    .withColumn("data", from_json(col("json_value"), schema)) \
    .select(
        col("data.date").alias("date_str"),
        to_timestamp(col("data.date"), "yyyy-MM-dd").alias("event_time"), # Convert to timestamp for windowing
        col("data.location").alias("location"),
        col("data.new_cases").alias("new_cases"),
        col("data.total_cases").alias("total_cases")
    ) \
    .filter(col("location").isNotNull() & col("new_cases").isNotNull() & col("total_cases").isNotNull())

# Define the window size for aggregation (e.g., 1 minute tumbling window)
windowed_aggregates = parsed_df \
    .withWatermark("event_time", "10 minutes") \
    .groupBy(
        window(col("event_time"), "1 minute"), # Tumbling window of 1 minute
        col("location")
    ) \
    .agg(
        sum("new_cases").alias("total_new_cases_in_window"),
        avg("new_cases").alias("avg_new_cases_per_entry"),
        max("new_cases").alias("max_new_cases_in_window"),
        sum("total_cases").alias("total_cases_sum_in_window"),
        avg("total_cases").alias("avg_total_cases_per_entry")
    ) \
    .select(
        col("window.start").cast(TimestampType()).alias("window_start"),
        col("window.end").cast(TimestampType()).alias("window_end"),
        col("location"),
        col("total_new_cases_in_window"),
        col("avg_new_cases_per_entry"),
        col("max_new_cases_in_window"),
        col("total_cases_sum_in_window"),
        col("avg_total_cases_per_entry")
    )

# --- Perform the Join with Countries Data ---
enriched_df = windowed_aggregates.join(
    countries_df,
    windowed_aggregates.location == countries_df.country_name,
    "inner" # Use 'left' if you want to keep all aggregated data even without country match
)

# --- Calculate New Cases Per Million ---
enriched_df = enriched_df.withColumn(
    "new_cases_per_million_in_window",
    col("total_new_cases_in_window") * lit(1000000.0) / col("country_population")
)

# Select and reorder columns to match the new MySQL schema
final_df = enriched_df.select(
    col("window_start"),
    col("window_end"),
    col("location"),
    col("total_new_cases_in_window"),
    col("avg_new_cases_per_entry"),
    col("max_new_cases_in_window"),
    col("total_cases_sum_in_window"),
    col("avg_total_cases_per_entry"),
    col("country_continent").alias("continent"),
    col("country_population").alias("population"),
    col("new_cases_per_million_in_window").cast(DecimalType(20, 4)),
    current_timestamp().alias("processing_time") # Use current_timestamp() directly now
)

# Write the aggregated and enriched data to MySQL
def upsertToMySQL(df, epoch_id):
    if df.isEmpty():
        print(f"Batch {epoch_id}: DataFrame is empty. Skipping write to MySQL.")
        return

    print(f"Batch {epoch_id}: Writing {df.count()} enriched rows to MySQL.")
    
    df.write \
        .format("jdbc") \
        .option("url", mysql_jdbc_url) \
        .option("dbtable", mysql_table) \
        .option("user", mysql_user) \
        .option("password", mysql_password) \
        .option("driver", "com.mysql.cj.jdbc.Driver") \
        .mode("append") \
        .save()
    
    print(f"Batch {epoch_id}: Successfully wrote {df.count()} enriched rows to MySQL.")


query = final_df \
    .writeStream \
    .outputMode("update") \
    .foreachBatch(upsertToMySQL) \
    .option("checkpointLocation", "/tmp/spark-checkpoint") \
    .trigger(processingTime="1 minute") \
    .start()

query.awaitTermination()
