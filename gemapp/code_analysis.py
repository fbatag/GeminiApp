import os
from vertexai.generative_models import Part
from google.cloud import storage

from .utils import getGenerativeModel, clearDir, get_temp_user_folder, save_local_file, zip_folder, get_blobs, getCodeFileExtenstion

storage_client = storage.Client()
CODE_BUCKET_NAME = os.environ.get("CODE_BUCKET_NAME", "gen-ai-app-code-") + storage_client.project
codeBucket  = storage_client.bucket(CODE_BUCKET_NAME, storage_client.project)
print(CODE_BUCKET_NAME)

PROG_LANGS = ("html", "py", "java", "js", "ts", "cs", "c", "cpp", "go", "rb", "php", "kt", "rs", "scala", "pl", "dart", "swift", "clj", "erl", "m")
MEDIA_SUPPORTED_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp", "video/mp4", "video/mpeg","video/mov","video/avi","video/x-flv","video/mpg","video/webm", "video/wmv","video/3gpp" ]
TXT_FILES = ["md", "txt"]

def get_code_midia_blobs(folder, include_txt_midia):
    if include_txt_midia:
        return get_blobs(codeBucket, folder, [PROG_LANGS, TXT_FILES], MEDIA_SUPPORTED_TYPES )
    return get_blobs(codeBucket, folder, [PROG_LANGS] )

def analizeCode(blobs_to_analyze, prompt, model_name):
    print("METHOD: analizeCode")
    model = getGenerativeModel(model_name)
    parts = [prompt]
    msg = "Files in context being considered: \n"
    for blob in blobs_to_analyze:
        if blob.content_type in MEDIA_SUPPORTED_TYPES:
            msg +="Adding file -> " + blob.name +"\n"
            uri = "gs://" + CODE_BUCKET_NAME + "/" + blob.name
            parts.append(Part.from_uri(uri=uri, mime_type=blob.content_type))
        else:
            msg +="Adding file -> " + blob.content_type + " - " + blob.name + "\n"
            uri = "gs://" + CODE_BUCKET_NAME + "/" + blob.name
            parts.append(Part.from_uri(uri=uri, mime_type="text/plain"))
    print(msg)
    generatedFiles = model.generate_content(parts)
    return generatedFiles.text

def generateCode(blobs_code, folder, human_prompt, model_name):
    print("METHOD: generateCode")
    generatedFiles = []
    model = getGenerativeModel(model_name)
    temp_user_folder = get_temp_user_folder()
    print("Cleaning temp_user_folder: " + temp_user_folder)
    clearDir(os.path.join(temp_user_folder,folder))
    for blob in blobs_code:
        uri = "gs://" + CODE_BUCKET_NAME + "/" + blob.name
        #try:
        prompt = [human_prompt, Part.from_uri(uri=uri, mime_type="text/plain")]
        response = model.generate_content(prompt)
        sub_folders = blob.name.split("/")
        generated_filename = "Gen_" + sub_folders[-1]
        print("Code: " + blob.name + " - Generated: " + generated_filename)
        file_tuple = (generated_filename, response.text)
        generatedFiles.append(file_tuple)
        save_local_file(generated_filename, response.text, sub_folders[:-1])
        """except Exception as e:
            print(e)
            file_tuple = ("Error no processamento" , str(e))
            generatedFiles.append(file_tuple)"""
    #try:
    print("Zipping the files")
    zip_folder(os.path.join(temp_user_folder,folder), os.path.join(temp_user_folder, "generated_code.zip"))
    """except Exception as e:
        print(e)
        file_tuple = ("Error ao zipar os arquivos gerados." , str(e))
        generatedFiles.append(file_tuple)"""
    return generatedFiles

