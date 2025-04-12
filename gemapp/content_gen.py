import os, json
from flask import request, render_template
from google.cloud import storage

from .utils import get_iap_user, getBucketFilesAndFolders, save_cli_file
from .generate_vertex import getGenerativeModel, getPartClass as getPart_vertex

storage_client = storage.Client()
CONTEXTS_BUCKET_NAME = os.environ.get("CONTEXTS_BUCKET_NAME", "gen-ai-app-contexts-") + storage_client.project
print(CONTEXTS_BUCKET_NAME)
contextsBucket = storage_client.bucket(CONTEXTS_BUCKET_NAME, storage_client.project)

#IS_GAE_ENV_STD = os.getenv('GAE_ENV', "") == "standard"

# Inicializa o array para armazenar os dados
global_loaded_prompts = dict()
global_contexts = dict()

def get_global_contexts():
    global global_contexts
    gc = global_contexts
    return gc

def getLoadedPrompts():
    user = get_iap_user()
    if user not in global_loaded_prompts:
        loadedPrompts = []
#        if IS_GAE_ENV_STD:
#            cachedLoadedPrompts = memcache.get(user)
#            if cachedLoadedPrompts is None:
#                #memcache.add(user, db.model_from_protobuf(loadedPrompts), 14400) # four hours expiration
#                memcache.add(user, json.dumps(loadedPrompts), 14400) # four hours expiration
#            else:
#                #loadedPrompts = db.model_from_protobuf(cachedLoadedPrompts)
#                loadedPrompts = json.loads(cachedLoadedPrompts)
        global_loaded_prompts[user] = loadedPrompts
    return global_loaded_prompts[user]

def load_prompts(prompts_json):
    print("METHOD: load_prompts")
    print("Loaded prompt size:" + str(len(prompts_json)))
    try:
        saveLoadedPrompts(json.loads(prompts_json))
        return ""
    except Exception as e:
        saveLoadedPrompts([])
        return "show_error_json_parser"
    
def view_prompts():
    print("METHOD: view_prompts")
    prompts = []
    for promptItem in getLoadedPrompts():
        prompts.append(prepare_prompt(promptItem))
    return render_template("view_prompts.html", prompts=prompts)

def saveLoadedPrompts(loadedPrompts):
    print("METHOD: saveLoadedPrompts")
    user = get_iap_user()
    if IS_GAE_ENV_STD:
        memcache.set(user, json.dumps(loadedPrompts))
        #memcache.set(user, db.model_to_protobuf(loadedPrompts))
    global_loaded_prompts[user] = loadedPrompts

def save_prompts_to_file():
    print("METHOD: save_prompts")
    loaded_prompts = getLoadedPrompts()
    return save_cli_file(json.dumps(loaded_prompts), request.form["filename_to_save"] , ".json")

def isPromptRepeated(prompt, project_name, filename):
    loaded_prompts = getLoadedPrompts()
    if len(loaded_prompts) > 0:
        #last_loaded_prompt, last_loaded_filename = loaded_prompts[len(loaded_prompts)-1]
        last_loaded_prompt, last_project, last_loaded_filename = loaded_prompts[-1]
        if last_loaded_prompt == prompt and last_project == project_name and filename == last_loaded_filename:
            return True
    return False

def uploadContext(project, file):
    print("METHOD: uploadContext")
    if not file:
        return
     # Faz o upload do arquivo para o bucket
    blob = contextsBucket.blob(project + "/" + file.filename)
    blob.upload_from_file(file, content_type=file.content_type)


def create_project(new_prj_name):
    print("METHOD: create_project", new_prj_name)
    blob = contextsBucket.blob(new_prj_name + "/")
    blob.upload_from_string("")
    
def deleteContext(folder, filename):
    print("METHOD: deleteContext")
    blob = contextsBucket.blob(folder + "/" + filename)    
    print("Deleting" + folder + "/"   + filename)
    try:
        blob.delete()
    except Exception as e:
        print(f"Error deleting object '{blob.name}': {e}")

def loadContextsBucket():
    print("METHOD: loadContextsBucket")
    global global_contexts
    global_contexts = getBucketFilesAndFolders(contextsBucket)
    
def delete_prompt_step(step_num_str):
    print("METHOD: delete_prompt_step")
    loaded_prompts = getLoadedPrompts()
    step_num = int(step_num_str)
    if step_num <= len(loaded_prompts):
        print(loaded_prompts[step_num-1])
        loaded_prompts.remove(loaded_prompts[step_num-1])
        saveLoadedPrompts(loaded_prompts)

def generate(model_name):
    print("METHOD: regenerate")
    print("Model: " + model_name)
    model = getGenerativeModel(model_name)
    chat = model.start_chat()
    
    token_consumption = []
    #total_token_consumption = [0,0,0]
    loaded_prompts = getLoadedPrompts()
    geminiResponse = []
    flatResponse = ""
    index = 1
    for promptItem in loaded_prompts:
        prompt = prepare_prompt(promptItem)
        try:
            stepResponse = chat.send_message(prompt)
            usage_metadata = stepResponse._raw_response.usage_metadata
            token_consumption.append((usage_metadata.prompt_token_count, usage_metadata.candidates_token_count, usage_metadata.total_token_count))
            geminiResponse.append(stepResponse.candidates[0].content.parts[0].text)
            flatResponse += "*** STEP " + str(index) + " ***\n" + stepResponse.candidates[0].content.parts[0].text +"\n\n"
        except Exception as e:
            print(e)
            token_consumption.append((0, 0, 0))
            geminiResponse.append(str(e))
            flatResponse += "*** STEP " + str(index) + " ***\n" + str(e) +"\n\n"
        index += 1
        # Diferentemente do que eu pensava incialmente, cada mensagem não é estanque:
        # A entrada do passo N+1 inclui os tokens de entrada do passo N+1 mais os passos de saída do passo N
        #tokenConsumptionMessage(usage_metadata, total_token_consumption)
    return render_template("generate.html", user=get_iap_user(),
                           loaded_prompts=loaded_prompts, geminiResponse=geminiResponse, flatResponse=flatResponse, model_name=model_name, 
                           token_consumption=token_consumption, total_token_consumption=token_consumption[-1])

def tokenConsumptionMessage(usage_metadata, token_consumption):
    token_consumption[0] += usage_metadata.prompt_token_count
    token_consumption[1] += usage_metadata.candidates_token_count
    token_consumption[2] += usage_metadata.total_token_count
    return 

def prepare_prompt(promptItem):
    print("METHOD: prepare_prompt")
    prompt, project_name, filename = promptItem
    if filename == "":
        return prompt
    uri = "gs://" + CONTEXTS_BUCKET_NAME +"/" + project_name + "/" + filename
    blob = contextsBucket.get_blob(project_name + "/" + filename)
    #print("file_type: ", file_type)
    print(blob)
    print("prompt: ", prompt, " - uri: ", uri, " - blob.content_type: ", blob.content_type)
    return [getPart_vertex().from_uri( uri=uri, mime_type=blob.content_type), prompt]
    #return [prompt, Part.from_uri( uri=uri, mime_type=file_type)]

def save_results():
    print("METHOD: save_results")
    return save_cli_file(request.form["geminiResponse"], request.form["filename_to_save"], ".txt")
