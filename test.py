import os
import json
from google.cloud import storage

FOLDERS =  "!<FOLDERS>!"
storage_client = storage.Client()
CONTEXTS_BUCKET_NAME = os.environ.get("CONTEXTS_BUCKET_NAME", "gen-ai-app-contexts-") + storage_client.project
CODE_BUCKET_NAME = os.environ.get("CODE_BUCKET_NAME", "gen-ai-app-code-") + storage_client.project
print(CONTEXTS_BUCKET_NAME)
print(CODE_BUCKET_NAME)
contextsBucket = storage_client.bucket(CONTEXTS_BUCKET_NAME, storage_client.project)
codeBucket  = storage_client.bucket(CODE_BUCKET_NAME, storage_client.project)
print(storage_client.project)

def getBucketFilesAndFolders(fromBucket, addFiles = True):
    print("METHOD: getBucketFilesAndFolders: Bucket Name: " + fromBucket.name)
    if not fromBucket.exists:
        raise Exception("O bucket "+ fromBucket.name + " não existe. É necessário cria-lo como parte da configuração do App")
    blobs = fromBucket.list_blobs()
    gc = dict()
    projects = []
    print("Blobs: " + str(blobs))
    for blob in blobs:
        # Extract folder name by splitting on '/' and taking everything but the last part
        print("Blob: " + blob.name)
        parts = blob.name.split('/')
        if len(parts) > 1:
            folder_name = parts[0]
        else:
            folder_name = "/"  # Root level
        # Add blob to the corresponding folder list
        if not folder_name in gc:
            projects.append(folder_name)
            gc[folder_name] = []
        if parts[-1] and addFiles:
            gc[folder_name].append(parts[-1])
    gc[FOLDERS]  = projects
    print("FIM - getBucketFilesAndFolders")
    return gc



def new_func():
    parts = "aaa/bbb".split("/")
    print(parts)
    parts = "/bbb".split("/")
    print(parts)
    parts = "aaa/".split("/")
    print(parts)


def listrDir(folder):
    for root, dirs, files in os.walk(folder):
        for file in files:
            print(os.path.join(root, file))
        for dir in dirs:
            print("DIR---------------: " + os.path.join(root, dir))

def clearDir(folder):
    folders = []
    for root, dirs, files in os.walk(folder):
        for file in files:
            os.remove(os.path.join(root, file))
        for dir in dirs:
            folders.append(os.path.join(root, dir))
    for folder in folders:
        os.rmdir(folder)

def main():
    #blobs = unitTestBucket.list_blobs(prefix="", delimiter="/")
    #blobs = unitTestBucket.list_blobs(delimiter="/")
    
    
    blobs= storage_client.bucket("dev-ghack-temp", storage_client.project).list_blobs()
    for blob in blobs:
        if blob.content_type in ["application/pdf", "image/png", "image/png", "video/mp4"]:
            print (blob.content_type)
            print (blob.name)
            
#clearDir("/Users/fbatagin/Desktop/Code/microservices-demo1")
import shutil
#print(getBucketFilesAndFolders(unitTestBucket))
main()