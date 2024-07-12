import os
import zipfile
import shutil
from flask import send_file

def get_temp_user_folder(user, sub_folders=[]):
    temp_dir = "/tmp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    temp_user_dir = user.replace("@", "_").replace(".", "_")
    temp_user_dir = os.path.join(temp_dir, temp_user_dir)
    if not os.path.exists(temp_user_dir):
        os.makedirs(temp_user_dir)
    for sub_folder in sub_folders:
        temp_user_dir = os.path.join(temp_user_dir, sub_folder)
        if not os.path.exists(temp_user_dir):
            os.makedirs(temp_user_dir)
    return temp_user_dir

def save_local_file(user, filename_to_save, content, sub_folders=[]):
    temp_dir = get_temp_user_folder(user, sub_folders)
    print("METHOD: save_cli_file: dir: " + temp_dir + " - filename: " + filename_to_save)
    tempfile_path = os.path.join(temp_dir, filename_to_save)
    with open(tempfile_path, "w") as f:
        f.write(content)
    return tempfile_path

def save_cli_file(user, content, filename_to_save, ext):
    print("METHOD: save_local_file: " + ext)
    tempfile_path = save_local_file(user, "temp.txt", content)
    return send_file(tempfile_path, as_attachment=True, download_name=ensureExtension(filename_to_save,ext))

def zip_folder(folder_path, output_filename):
    print("METHOD: zip_folder: folder_path: " + folder_path + " - output_filename: " + output_filename)
    with zipfile.ZipFile(output_filename, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                # Remove the folder path from the file path to avoid including it in the ZIP file
                arcname = os.path.relpath(file_path, start=folder_path)
                zip_file.write(file_path, arcname=arcname)
    clearDir(folder_path)

def donwload_zip_file(user, filename_to_save):
    print("METHOD: index -> donwload_zip_file")
    # vefifica se o nome do rquivo tem a extensão .zio, senão adiciona
    origin = os.path.join(get_temp_user_folder(user), "unit_tests.zip")
    return send_file(origin,  as_attachment=True, download_name=ensureExtension(filename_to_save, ".zip"))

def clearDir(folder):
    print("METHOD: clearDir: " + folder)
    try:
        shutil.rmtree(folder)
        print(f"Folder '{folder}' deleted.")
    except FileNotFoundError:
        print(f"Folder '{folder}' not found.")
    except Exception as e:
        print(f"Deleting folder '{folder}' failed: {e}")    

def getCodeFileExtenstion(filename):
    parts = filename.split(".")
    return parts[-1].lower()

def get_blobs(codeBucket, folder, file_types_array, blob_types=[]):
    print("METHOD: get_blobs_to_analyze")
    blobs = codeBucket.list_blobs(prefix=folder)
    blobsToAnalize = []
    for blob in blobs:
        if blob.size > 10: # why 10 ? it cloiud be 0, but just excluding very small content
            for file_types in file_types_array:
                if getCodeFileExtenstion(blob.name) in file_types:
                    blobsToAnalize.append(blob)
            if blob.content_type in blob_types:
                blobsToAnalize.append(blob)
    return blobsToAnalize

def ensureExtension(filename, ext):
    if not filename.endswith(ext):
        filename += ext
    return filename
                    