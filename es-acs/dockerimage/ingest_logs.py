#!/usr/bin/env python

from elasticsearch import Elasticsearch
import json
import random
from datetime import datetime
import lorem
import logging

# Configure logging to write to stdout and stderr
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Elasticsearch server settings
es = Elasticsearch("http://elasticsearch-v1.elasticsearch.svc.cluster.local:9200")

# Validate Elasticsearch connection
if not es.ping():
    logging.error('Elasticsearch connection failed')
    exit(1)

# Index name
index_name = "acstor"

# Number of dummy logs to generate
num_logs = 100000

# Validate Elasticsearch index settings
index_info = es.indices.get(index=index_name)
if not index_info:
    logging.error(f'Failed to get information about the index "{index_name}"')
    exit(1)

try:
    # Generate and ingest dummy logs
    for i in range(1, num_logs + 1):
        log_entry = {
            "@timestamp": datetime.now().isoformat(),
            "message": lorem.sentence(),
            "log_level": random.choice(["INFO", "ERROR", "DEBUG", "WARNING"]),
            "log_source": random.choice(["AppServer", "WebServer", "Database", "Worker"]),
        }

        # Ingest the log entry into the index
        es.index(index=index_name, body=json.dumps(log_entry))

        if i % 1000 == 0:
            print(f"Ingested {i} logs")

    print(f"Successfully ingested {num_logs} dummy logs into the '{index_name}' index.")
except Exception as e:
    logging.error(f'Error during data ingestion: {e}')
    exit(1)

# Log a success message
logging.info('Script completed successfully')
