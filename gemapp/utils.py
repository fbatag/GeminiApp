import os
import zipfile
import shutil
from flask import send_file, request
from vertexai.generative_models import GenerativeModel
import vertexai.preview.generative_models as generative_models

FOLDERS =  "!<FOLDERS>!"

generation_config_flash = {
    "max_output_tokens": 8192,
    "temperature": 0.5,
    "top_p": 0.95,
}

generation_config_pro = {
    "max_output_tokens": 8192, # o modelo responde 32768, mas tanto a doc quanto a execução não aceita esse valor
    "temperature": 0.5,
    "top_p": 0.95,
}
safety_settings = {
    generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
}

# ATENÇÃO: Os parãmetros abaixo somente funcionam com prompt texto. Se um arquivo é incluido, dai erro "400 Request contains an invalid argument." 
#safety_settings_none = {
 #   #generative_models.HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
 #   generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_NONE,
 #   generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
 #   generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_NONE,
 #   generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
#}
def getGenerativeModel(model_name):
    if model_name == "gemini-1.5-flash-002":
        generation_config = generation_config_flash
    else:
        generation_config = generation_config_pro

    return GenerativeModel(model_name, generation_config=generation_config, safety_settings=safety_settings)

def get_iap_user():
    user = request.headers.get('X-Goog-Authenticated-User-Email', "None")
    if user != "None":
        user = user.replace("accounts.google.com:","")
    return user

def get_blobs(codeBucket, folder, file_types_array, blob_types=[]):
    print("METHOD: get_blobs_to_analyze")
    blobs = codeBucket.list_blobs(prefix=folder)
    blobsToAnalize = []
    for blob in blobs:
        if blob.size > 5: # why 5 ? it cloiud be 0, but just excluding very small content
            for file_types in file_types_array:
                if getCodeFileExtenstion(blob.name) in file_types:
                    blobsToAnalize.append(blob)
            if blob.content_type in blob_types:
                blobsToAnalize.append(blob)
    return blobsToAnalize

def getBucketFilesAndFolders(fromBucket, addFiles = True):
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
            projects.append(folder_name)
            gc[folder_name] = []
        if parts[-1] and addFiles:
            gc[folder_name].append(parts[-1])
    gc[FOLDERS]  = projects
    return gc
    
def get_temp_user_folder(sub_folders=[]):
    temp_dir = "/tmp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    user = get_iap_user()
    temp_user_dir = user.replace("@", "_").replace(".", "_")
    temp_user_dir = os.path.join(temp_dir, temp_user_dir)
    if not os.path.exists(temp_user_dir):
        os.makedirs(temp_user_dir)
    for sub_folder in sub_folders:
        temp_user_dir = os.path.join(temp_user_dir, sub_folder)
        if not os.path.exists(temp_user_dir):
            os.makedirs(temp_user_dir)
    return temp_user_dir

def save_local_file(filename_to_save, content, sub_folders=[]):
    temp_dir = get_temp_user_folder(sub_folders)
    print("METHOD: save_cli_file: dir: " + temp_dir + " - filename: " + filename_to_save)
    tempfile_path = os.path.join(temp_dir, filename_to_save)
    with open(tempfile_path, "w") as f:
        f.write(content)
    return tempfile_path

def save_cli_file(content, filename_to_save, ext):
    print("METHOD: save_local_file: " + ext)
    tempfile_path = save_local_file("temp.txt", content)
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

def donwload_zip_file(filename_to_save):
    print("METHOD: index -> donwload_zip_file")
    # vefifica se o nome do rquivo tem a extensão .zio, senão adiciona
    origin = os.path.join(get_temp_user_folder(), "generated_code.zip")
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

def ensureExtension(filename, ext):
    if not filename.endswith(ext):
        filename += ext
    return filename
                    
def excludeBlobFolder(codeBucket, folder):
    blobs = codeBucket.list_blobs(prefix=folder)
    for blob in blobs:
        blob.delete()
    return

