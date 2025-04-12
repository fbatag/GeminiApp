import os
from google.cloud import storage

from .utils import clearDir, get_temp_user_folder, save_local_file, zip_folder, get_blobs
from .generate_genai import getPartClass as getPart_genai, generate as generate_genai
from .generate_vertex import getPartClass as getPart_vertex, generate as generate_vertex

storage_client = storage.Client()
CODE_BUCKET_NAME = os.environ.get("CODE_BUCKET_NAME", "gen-ai-app-code-") + storage_client.project
codeBucket  = storage_client.bucket(CODE_BUCKET_NAME, storage_client.project)
print(CODE_BUCKET_NAME)

PROG_LANGS = ("html", "py", "java", "js", "ts", "cs", "c", "cpp", "go", "rb", "php", "kt", "rs", "scala", "pl", "dart", "swift", "clj", "erl", "m", "pas", "dfm", "dpr", "resv")
MEDIA_SUPPORTED_TYPES = ["application/pdf", "audio/ogg", "audio/mp3", "audio/wav", "audio/acc", "audio/acc", "image/jpeg", "image/png", "image/webp", "video/mp4", "video/mpeg","video/mov","video/avi","video/x-flv","video/mpg","video/webm", "video/wmv","video/3gpp" ]
TXT_FILES = ["md", "txt"]

def get_code_media_blobs(folder, include_txt_media):
    print("METHOD: get_code_media_blobs - " + str(include_txt_media))
    if include_txt_media:
        return get_blobs(codeBucket, folder, [PROG_LANGS, TXT_FILES], MEDIA_SUPPORTED_TYPES )
    return get_blobs(codeBucket, folder, [PROG_LANGS, TXT_FILES] )

def getBlobType(blob):
    if blob.content_type in MEDIA_SUPPORTED_TYPES:
        return blob.content_type
    return "text/plain"

def getBlobUri(blob):
    return "gs://" + CODE_BUCKET_NAME + "/" + blob.name

def generate(model_name, parts, useVertex):
    print("METHOD: generate - " + str(useVertex))
    if useVertex:
        return generate_vertex(model_name, parts)
    else:
        return generate_genai(model_name, parts)
      
def initializeParts(prompt, useVertex):
    if useVertex:
        return [ prompt ]
    else:
        return [ getPart_genai().from_text(text=prompt) ]
    
def getPartFromBlob(blob, useVertex):
    if useVertex:
        return getPart_vertex().from_uri(uri=getBlobUri(blob), mime_type=getBlobType(blob)) 
    else:
        return getPart_genai().from_uri(file_uri=getBlobUri(blob), mime_type=getBlobType(blob))

def analizeCode(blobs_to_analyze, human_prompt, model_name, useVertex = True):
    print("METHOD: analizeCode")
    parts = initializeParts(human_prompt, useVertex)
    msg = "\n\n***** Arquivos considerados na análise: *****\n\n"
    for blob in blobs_to_analyze:
        msg += getBlobType(blob) + " - " + blob.name + "\n"
        parts.append(getPartFromBlob(blob, useVertex))
    print(msg)
    return generate(model_name, parts, useVertex) + msg

def getTargetName(blob):
    sub_folders = blob.name.split("/")
    generated_filename = "Gen_" + sub_folders[-1]
    print("Code: " + blob.name + " - Generated: " + generated_filename)
    return generated_filename, sub_folders[:-1]
    
def generateCode(blobs_code, folder, human_prompt, model_name, lines_chunck_size = 0, useVertex = True):
    print("METHOD: generateCode - lines_chunck_size: " + str(lines_chunck_size))
    generatedFiles = []
    temp_user_folder = get_temp_user_folder()
    print("Cleaning temp_user_folder: " + temp_user_folder)
    clearDir(os.path.join(temp_user_folder,folder))
    for blob in blobs_code:
        #try:
        genFilename, sub_folder = getTargetName(blob)
        if lines_chunck_size == 0:
            response = codeFileGeneration(blob, human_prompt, model_name, useVertex)
        else:
            response = codeFileGenerationLongOutput(blob, human_prompt, model_name, lines_chunck_size, useVertex)
        save_local_file(genFilename, response, sub_folder)
        file_tuple = (genFilename, response)
        generatedFiles.append(file_tuple)
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

def codeFileGeneration(blob, human_prompt, model_name, useVertex):
    print("METHOD: codeFileGeneration")
    parts = initializeParts(human_prompt, useVertex)
    parts.append(getPartFromBlob(blob, useVertex))
    return generate(model_name, parts, useVertex)

def codeFileGenerationLongOutput(blob, human_prompt, model_name, lines_chunck_size, useVertex):
    print("METHOD: codeFileGenerationLongOutput")
    chunks = split_string_by_lines(blob, lines_chunck_size)
    response = ""
    for chunk in chunks:
        parts = initializeParts(human_prompt, useVertex)
        parts.append(getPartFromBlob(blob, useVertex))
        response += generate(model_name, parts, useVertex) + "\n\n"
    title = "O arquivo " + blob.name + " foi processado em " + str(len(chunks)) + " partes de " + str(lines_chunck_size) + " linhas cada.\n\n"
    return title + response

def split_string_by_lines(blob, lines_chunck_size):
    content = blob.download_as_string().decode("utf-8")
    lines = content.splitlines()
    chunks = []
    for i in range(0, len(lines), lines_chunck_size):
        chunk = '\n'.join(lines[i:i + lines_chunck_size])
        #print("****** chunk ******")
        #print(chunk)
        chunks.append(chunk)
    return chunks