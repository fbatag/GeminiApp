import os
import json
from google.cloud import storage

FOLDERS =  "!<FOLDERS>!"
storage_client = storage.Client()
UNIT_TESTS_BUCKET_NAME = os.environ.get("UNIT_TESTS_BUCKET_NAME", "gen-ai-app-unit-tests-") + storage_client.project
unitTestBucket = storage_client.bucket(UNIT_TESTS_BUCKET_NAME, storage_client.project)

def getBucketFilesAndFolders(fromBucket):
    print("METHOD: getBucketFilesAndFolders: Bucket Name: " + fromBucket.name)
    if not fromBucket.exists:
        raise Exception("O bucket "+ fromBucket.name + " não existe. É necessário cria-lo como parte da configuração do App")
    blobs = fromBucket.list_blobs()
    gc = dict()
    projects = []
    for blob in blobs:
        # Extract folder name by splitting on '/' and taking everything but the last part
        parts = blob.name.split('/')
        if len(parts) > 1:
            folder_name = parts[0]
        else:
            folder_name = "/"  # Root level
        # Add blob to the corresponding folder list
        if not folder_name in gc:
            gc[folder_name] = []
            projects.append(folder_name)
        if parts[-1]:
            gc[folder_name].append(parts[-1])
    gc[FOLDERS]  = projects
    return gc

def main():
    #blobs = unitTestBucket.list_blobs(prefix="", delimiter="/")
    #blobs = unitTestBucket.list_blobs(delimiter="/")
    blobs = unitTestBucket.list_blobs(prefix="GeminiApp/")
    #blobs = unitTestBucket.list_blobs()
    projects = []
    for blob in blobs:
        print (blob.name)
        if blob.name.endswith("/"):
            #folder = blob.name.strip('/')
            parts = blob.name.split('/')
            if len(parts) == 1:
                # Extract folder name by splitting on '/' and taking everything but the last part
                projects.append(parts[0])    

main()
print(getBucketFilesAndFolders(unitTestBucket))
