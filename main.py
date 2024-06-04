import os
from flask import Flask, render_template, request, session, redirect, url_for, send_file
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
import vertexai.preview.generative_models as generative_models
from google.cloud import vision
from google.cloud import storage
from google.appengine.api import memcache, wrap_wsgi_app
from google.appengine.ext import db, ndb

#PROJECT_ID = os.environ.get("PROJECT_ID")
REGION = os.environ.get("REGION")
print(REGION)
#GAE = os.environ.get("GAE", "TRUE").upper() == "TRUE"
#GAE_APP_ID = os.environ.get("GAE_APP_ID", "default")
# Create a Flask app
print("(RE)LOADING APPLICATION")
app = Flask(__name__)
#GAE_APPLICATION = os.getenv('GAE_APPLICATION', "")
#print("GAE_APPLICATION: " + GAE_APPLICATION)
#GAE_SERVICE = os.getenv('GAE_SERVICE', "")
#GOOGLE_CLOUD_PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT', "4ab7c")
IS_GAE_ENV_STD = os.getenv('GAE_ENV', "") == "standard"
if IS_GAE_ENV_STD:
    app.wsgi_app = wrap_wsgi_app(app.wsgi_app)

storage_client = storage.Client()
CONTEXTS_BUCKET_NAME = os.environ.get("CONTEXTS_BUCKET_NAME", "gen-ai-app-contexts-") + storage_client.project
CODE_BUCKET_NAME = os.environ.get("CODE_BUCKET_NAME", "gen-ai-app-code-") + storage_client.project
print(CONTEXTS_BUCKET_NAME)
print(CODE_BUCKET_NAME)
contextsBucket = storage_client.bucket(CONTEXTS_BUCKET_NAME, storage_client.project)
codeBucket  = storage_client.bucket(CODE_BUCKET_NAME, storage_client.project)

vertexai.init()

generation_config = {
    "max_output_tokens": 8192,
    "temperature": 1,
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

# Inicializa o array para armazenar os dados
global_loaded_prompts = dict()
global_contexts = dict()
FOLDERS =  "!<FOLDERS>!"
global_code_files = dict()
global_code_files[FOLDERS] = []
PROG_LANGS = ("py", "java", "js", "ts", "cs", "c", "cpp", "go", "rb", "php", "kt", "rs", "scala", "pl", "dart", "swift", "clj", "erl", "m")



def get_iap_user():
    return request.headers.get('X-Goog-Authenticated-User-Email', "None")

def get_temp_file():
    tempfile = request.headers.get('X-Goog-Authenticated-User-Email', "None")
    tempfile = tempfile.replace("@", "_").replace(".", "_")
    tempfile += ".txt"
    return tempfile

def getLoadedPrompts():
    user = get_iap_user()
    if user not in global_loaded_prompts:
        loadedPrompts = []
        if IS_GAE_ENV_STD:
            cachedLoadedPrompts = memcache.get(user)
            if cachedLoadedPrompts is None:
                #memcache.add(user, db.model_from_protobuf(loadedPrompts), 14400) # four hours expiration
                memcache.add(user, json.dumps(loadedPrompts), 14400) # four hours expiration
            else:
                #loadedPrompts = db.model_from_protobuf(cachedLoadedPrompts)
                loadedPrompts = json.loads(cachedLoadedPrompts)
        global_loaded_prompts[user] = loadedPrompts
    return global_loaded_prompts[user]

def saveLoadedPrompts(loadedPrompts):
    print("METHOD: saveLoadedPrompts")
    user = get_iap_user()
    if IS_GAE_ENV_STD:
        memcache.set(user, json.dumps(loadedPrompts))
        #memcache.set(user, db.model_to_protobuf(loadedPrompts))
    global_loaded_prompts[user] = loadedPrompts

def isPromptRepeated(prompt, project_name, filename):
    loaded_prompts = getLoadedPrompts()
    if len(loaded_prompts) > 0:
        #last_loaded_prompt, last_loaded_filename = loaded_prompts[len(loaded_prompts)-1]
        last_loaded_prompt, last_project, last_loaded_filename = loaded_prompts[-1]
        if last_loaded_prompt == prompt and last_project == project_name and filename == last_loaded_filename:
            return True
    return False

@app.route("/", methods=["GET", "POST"])
def index():
    loaded_prompts = getLoadedPrompts()
    print("METHOD: index -> " + request.method + " prompts size: " + str(len(loaded_prompts)))
    clicked_button = request.form.get('clicked_button', "NOT_FOUND")
    print("clicked_button: ", clicked_button)
    if clicked_button == "load_context_step_btn_nofile" or clicked_button == "load_context_step_btn":
        prompt = request.form.get("txt_prompt", "").strip()
        context_filename = request.form.get("contexts_slc","")
        if context_filename == "" or clicked_button == "load_context_step_btn_nofile":
            context_filename =""
            project_name =""
        else:
            project_name = request.form.get("projects_slc","")
        if prompt == "":
            return renderIndex(any_error="show_error_is_empty")
        if isPromptRepeated(prompt, project_name, context_filename):
            return renderIndex(any_error="show_error_repeated")
        loaded_prompts.append((prompt, project_name, context_filename))
        saveLoadedPrompts(loaded_prompts)
        return renderIndex(keep_prompt=False)
    elif clicked_button == "delete_step_btn": 
        delete_prompt_step(request.form["step_to_delete"])
    elif clicked_button == "update_contexts_btn": 
        return proceed("loadContextsBucket")
    elif clicked_button == "loadContextsBucket":
        loadContextsBucket()
    elif clicked_button == "manage_contexts_btn":
        return renderIndex("context.html")
    elif clicked_button == "upload_context_btn":
        uploadContext(request.form["projects_slc"],request.files["load_context_file"])
        loadContextsBucket()
        return renderIndex("context.html")
    elif clicked_button == "delete_context_btn":
        deleteContext(request.form["projects_slc"], request.form["context_to_delete"])
        loadContextsBucket()
        return renderIndex("context.html")
    elif clicked_button == "create_prj_btn":
        create_project(request.form["new_prj_name"])
        loadContextsBucket()
        return renderIndex("context.html")
    #elif clicked_button == "projects_slc":
    #    return renderIndex()
    elif clicked_button == "regenerate_btn":
        return proceed("regenerate")
    elif clicked_button == "regenerate":
        return generate()
    elif clicked_button == "reset":
        return reset()
    elif clicked_button == "view":
        return view()
    elif clicked_button == "save_prompts":
        return save_prompts()
    elif clicked_button == "load_prompts_btn":
        return load_prompts(request.form["prompt_history_json"])
    # generate.html buttons
    elif clicked_button == "save_result_btn":
        return save_results()
    elif clicked_button == "update_code_files_btn":
        return proceed("update_code_files_btn", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "loadCodeBucketFolders":
        loadCodeBucketFolders()
        return renderIndex(activeTab="tabCodeFilesGeneration")
    elif clicked_button == "projects_code_slc":
        return renderIndex(activeTab="tabCodeFilesGeneration")
    elif clicked_button == "generate_unit_tests_1x_btn" or clicked_button == "generate_unit_tests_1a1_btn" or clicked_button == "generate_save_unit_tests_1a1_btn":
        return render_template("proceed.html", target_method=clicked_button, model_name=request.form.get("model_name",""), 
                               folder = request.form["projects_code_slc"], prog_lang = request.form["prog_lang_exts_slc"])
    elif clicked_button == "show_generate_unit_tests_1a1_btn":
        return renderIndex(activeTab="tabCodeFilesGeneration", codeResponse = generate_unit_tests_one_by_one())
    elif clicked_button == "show_generate_unit_tests_1x_btn":
        return renderIndex(activeTab="tabCodeFilesGeneration", codeResponse = generate_unit_tests_once())
    elif clicked_button == "exec_generate_save_unit_tests_1a1_btn":
        return renderIndex(activeTab="tabCodeFilesGeneration", codeResponse = generate_unit_tests_one_by_one(save=True))
    elif clicked_button == "save_unit_tests_btn":
        return save_unit_tests()
    return renderIndex()

def renderIndex(page="index.html", any_error="", keep_prompt=True, activeTab="tabContextGeneration",codeResponse=""):
    print("METHOD: renderIndex -> " + any_error + " keep_prompt: " + str(keep_prompt))
    global global_contexts
    gc = global_contexts
    #activeTab = request.form.get("activeTab", "tabContextGeneration")
    #print("activeTab: ", activeTab)
    if not FOLDERS in gc:
        return proceed("loadContextsBucket")
    choosen_model_name = request.form.get("model_name", "gemini-1.5-flash-preview-0514")
    txt_prompt = ""
    if keep_prompt:
        txt_prompt = request.form.get("txt_prompt", "")
    context_projects = []
    contexts = []
    project = request.form.get("projects_slc", "")
    if project == "" and len(gc[FOLDERS]) > 0:
        project = gc[FOLDERS][0]
    if project != "" and len(gc[FOLDERS]) > 0:
        context_projects = gc[FOLDERS]
        contexts = contexts=gc[project]
    prog_land_exts = []
    project_lang = request.form.get("projects_code_slc", "")
    if project_lang == "" and len(global_code_files[FOLDERS]) > 0:
        project_lang = global_code_files[FOLDERS][0]
    if project_lang != "":
        prog_land_exts = global_code_files[project_lang]
    print("project_lang=" + project_lang + " - global_code_files[FOLDERS]=" + str(global_code_files[FOLDERS]) + " - prog_land_exts=" + str(prog_land_exts))
    
    #print("choosen_model_name="+ choosen_model_name +" project=" + project + " projects=" + str(gc[FOLDERS]) + " contexts=" + str(gc[project]))
    return render_template(page, user=get_iap_user(), loaded_prompts=getLoadedPrompts(), choosen_model_name=choosen_model_name, 
                           project=project, projects=context_projects, contexts=contexts, txt_prompt=txt_prompt, 
                           projects_code=global_code_files[FOLDERS], prog_land_exts=prog_land_exts, project_prog_lang=project_lang,
                           activeTab=activeTab, codeResponse=codeResponse,
                           any_error=any_error)
    

def create_project(new_prj_name):
    print("METHOD: create_project", new_prj_name)
    blob = contextsBucket.blob(new_prj_name + "/")
    blob.upload_from_string("")
    
def uploadContext(project, file):
    print("METHOD: uploadContext")
    if file:
        # Faz o upload do arquivo para o bucket
        blob = contextsBucket.blob(project + "/" + file.filename)
        blob.upload_from_file(file, content_type=file.content_type)
        #try:
        #    convertToText(project, file)
        #except Exception as e:
        #    print(e)

def deleteContext(folder, filename):
    print("METHOD: deleteContext")
    blob = contextsBucket.blob(folder + "/" + filename)    
    print("Deleting" + folder + "/"   + filename)
    try:
        blob.delete()
    except Exception as e:
        print(f"Error deleting object '{blob.name}': {e}")

def convertToText(folder, file):
    if file.content_type != "application/pdf":
        return
    print("METHOD: convertToText", folder, file.filename)
    src_uri = uri=getGsUri(folder, file.filename)
    dst_uri = uri=getGsUri(folder, file.filename.replace(".pdf", ".txt"))
    client = vision.ImageAnnotatorClient()
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    gcs_source = vision.GcsSource(uri=src_uri)
    input_config = vision.InputConfig(gcs_source=gcs_source, mime_type=file.content_type)
    gcs_destination = vision.GcsDestination(uri=dst_uri)
    output_config = vision.OutputConfig(gcs_destination=gcs_destination, batch_size=2)
    async_request = vision.AsyncAnnotateFileRequest(
       features=[feature], input_config=input_config, output_config=output_config
    )
    operation = client.async_batch_annotate_files(requests=[async_request])
    operation.result(timeout=420)

def loadContextsBucket():
    print("METHOD: loadContextsBucket")
    global global_contexts
    global_contexts = getBucketFilesAndFolders(contextsBucket)

def loadCodeBucketFolders():
    print("METHOD: loadCodeBucketFolders")
    global global_code_files
    global_code_files = getBucketFilesAndFolders(codeBucket, True)
    
def getBucketFilesAndFolders(fromBucket, groupByExt = False):
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
        if parts[-1]:
            if groupByExt:
                ext = parts[-1].split(".")[-1].lower()
                if ext in PROG_LANGS and not ext in gc[folder_name]:
                    gc[folder_name].append(ext)
            else:
                gc[folder_name].append(parts[-1])
    gc[FOLDERS]  = projects
    return gc

def proceed(target_method="regenerate",bucket=CONTEXTS_BUCKET_NAME):
    print("METHOD: proceed" + " target_method: " + target_method)
    if target_method == "regenerate":
        if len(getLoadedPrompts()) == 0:
            return renderIndex(any_error="show_error_no_prompts")
    return render_template("proceed.html", target_method=target_method, model_name=request.form.get("model_name",""), bucket=bucket, txt_prompt = request.form.get("txt_prompt", ""))

def generate():
    print("METHOD: regenerate")
    model_name = request.form["model_name"]
    print("Model: " + model_name)
    model = GenerativeModel(model_name, generation_config=generation_config, safety_settings=safety_settings)
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
    return render_template("generate.html", loaded_prompts=loaded_prompts, geminiResponse=geminiResponse, flatResponse=flatResponse, model_name=model_name, 
                           token_consumption=token_consumption, total_token_consumption=token_consumption[-1])

def tokenConsumptionMessage(usage_metadata, token_consumption):
    token_consumption[0] += usage_metadata.prompt_token_count
    token_consumption[1] += usage_metadata.candidates_token_count
    token_consumption[2] += usage_metadata.total_token_count
    return 

def getGsUri(folder, filename):
    return "gs://" + CONTEXTS_BUCKET_NAME +"/" + folder + "/" + filename

def prepare_prompt(promptItem):
    print("METHOD: prepare_prompt")
    prompt, project_name, filename = promptItem
    print("prompt: ", prompt, " - project: ", project_name, " - filename: ", filename)
    if filename == "":
        return prompt
    uri=getGsUri(project_name, filename)
    file_type = getFileType(filename)
    #print("file_type: ", file_type)
    #print("uri: ", uri)
    return [Part.from_uri( uri=uri, mime_type=file_type), prompt]
    #return [prompt, Part.from_uri( uri=uri, mime_type=file_type)]

def getFileType(filename):
    print("METHOD: getFileType")
    file_type = filename.split(".").pop()
    if  file_type == "mp4":
        return "video/mp4"
    elif file_type == "pdf":
        return "application/pdf"
    return "text/plain"

def reset():
    print("METHOD: reset")
    saveLoadedPrompts([])
    print("Contexto limpo!")
    return renderIndex()

def view():
    print("METHOD: view")
    prompts = []
    for promptItem in getLoadedPrompts():
        prompts.append(prepare_prompt(promptItem))
    return render_template("view_prompts.html", prompts=prompts)

def load_prompts(prompts_json):
    print("METHOD: load_prompts")
    print("Loaded prompt size:" + str(len(prompts_json)))
    try:
        saveLoadedPrompts(json.loads(prompts_json))
        return renderIndex()
    except Exception as e:
        saveLoadedPrompts([])
        return renderIndex(any_error="show_error_json_parser")

def save_prompts():
    print("METHOD: save_prompts")
    loaded_prompts = getLoadedPrompts()
    return save_local_file(json.dumps(loaded_prompts), ".json")

def save_unit_tests():
    print("METHOD: save_unit_tests")
    return save_local_file(request.form["codeResponse"], "." + request.form["prog_lang_exts_slc"])

def save_results():
    print("METHOD: save_results")
    return save_local_file(request.form["geminiResponse"], ".txt")

def save_local_file(content, ext):
    print("METHOD: save_local_file: " + ext)
    filename_to_save = request.form["filename_to_save"] + ext
    return save_cli_file(request.form["filename_to_save"] + ext, content)

def save_cli_file( filename, content):
    print("METHOD: save_cli_file: " + filename)
    tempfile_path = os.path.join(tempDir(), get_temp_file())
    with open(tempfile_path, "w") as f:
        f.write(content)
    return send_file(tempfile_path, as_attachment=True, download_name=filename)

def delete_prompt_step(step_num_str):
    print("METHOD: delete_prompt_step")
    loaded_prompts = getLoadedPrompts()
    step_num = int(step_num_str)
    if step_num <= len(loaded_prompts):
        print(loaded_prompts[step_num-1])
        loaded_prompts.remove(loaded_prompts[step_num-1])
        saveLoadedPrompts(loaded_prompts)


def tempDir():
    temp_dir = "/tmp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return temp_dir

def clearDir():
    temp_dir = tempDir()
    files = os.listdir(temp_dir)
    for file in files:
        os.remove(os.path.join(temp_dir, file))

def getFileExtenstion(filename):
    parts = filename.split(".")
    return parts[-1].lower()

def generate_unit_tests_one_by_one(save=False):
    print("METHOD: generate_unit_tests")
    model_name = request.form["model_name"]
    folder = request.form["projects_code_slc"] + "/"
    prog_lang = request.form["prog_lang_exts_slc"]
    print("prog_lang: " + prog_lang)
    blobs = codeBucket.list_blobs(prefix=folder)
    codeResponse = []
    model = GenerativeModel(model_name, generation_config=generation_config, safety_settings=safety_settings)
    for blob in blobs:
        if getFileExtenstion(blob.name) == prog_lang:
            uri = "gs://" + CODE_BUCKET_NAME + "/" + blob.name
            try:
                prompt = ["Generate unit tests for this code", Part.from_uri(uri=uri, mime_type="text/plain")]
                response = model.generate_content(prompt)
                file_tuple = ("Test_" + blob.name, response.text)
                codeResponse.append(file_tuple)
                if (save):
                    save_cli_file("Test_" + blob.name, response.text) # não dá pra salvar um por um, então salvar no bucket                
            except Exception as e:
                print(e)
        else:
            print("SKIPED -> " + blob.name)
    return codeResponse

def generate_unit_tests_once():
    print("METHOD: generate_unit_tests")
    model_name = request.form["model_name"]
    folder = request.form["projects_code_slc"] + "/"
    prog_lang = request.form["prog_lang_exts_slc"]
    print("prog_lang: " + prog_lang)
    blobs = codeBucket.list_blobs(prefix=folder)
    model = GenerativeModel(model_name, generation_config=generation_config, safety_settings=safety_settings)
    parts = ["Generate unit tests for this code"]
    for blob in blobs:
        if getFileExtenstion(blob.name) == prog_lang:
            uri = "gs://" + CODE_BUCKET_NAME + "/" + blob.name
            parts.append(Part.from_uri(uri=uri, mime_type="text/plain"))
        else:
            print("SKIPED -> " + blob.name)

    codeResponse = model.generate_content(parts)
    return [ ("Test_all"+"."+prog_lang, codeResponse.text) ]


if __name__ == "__main__":
    app.run(debug=True)
