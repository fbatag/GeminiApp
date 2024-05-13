import os
import json
from google.cloud import storage


def getBucket(CONTEXTS_BUCKET_NAME):
    storage_client = storage.Client()
    # Cria um bucket se ele não existir
    bucket = storage_client.bucket(CONTEXTS_BUCKET_NAME)
    if not bucket.exists():
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        #bucket.create(location=REGION)
        bucket.create()
        print("Bucket {} created".format(CONTEXTS_BUCKET_NAME))
    return bucket  

#getBucket("lmkjnhdududud")
REGION = os.environ.get("REGION")
print(REGION)