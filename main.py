import os
from flask import Flask, render_template, request
#from flask import session, redirect, url_for
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
import vertexai.preview.generative_models as generative_models
from google.cloud import storage
from google.appengine.api import memcache, wrap_wsgi_app
#from google.appengine.ext import db, ndb
from gemapp.utils import donwload_zip_file, save_cli_file
from gemapp.code_analysis import CODE_BUCKET_NAME, codeBucket, get_code_midia_blobs, generateUnitTests, generate_code_analysis

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
#else:
#    app.run(host='0.0.0.0', port=8080, mult)

storage_client = storage.Client()
CONTEXTS_BUCKET_NAME = os.environ.get("CONTEXTS_BUCKET_NAME", "gen-ai-app-contexts-") + storage_client.project
print(CONTEXTS_BUCKET_NAME)
contextsBucket = storage_client.bucket(CONTEXTS_BUCKET_NAME, storage_client.project)

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
global_code_projects =[]
PROG_LANGS = ("py", "java", "js", "ts", "cs", "c", "cpp", "go", "rb", "php", "kt", "rs", "scala", "pl", "dart", "swift", "clj", "erl", "m")
MEDIA_SUPPORTED_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp", "video/mp4", "video/mpeg","video/mov","video/avi","video/x-flv","video/mpg","video/webm", "video/wmv","video/3gpp" ]

PROMPT_SUGESTIONS=["", "Crie casos de teste a partir do sistema descrito no video:", "Crie casos de teste a partir do sistema descrito no documento:"]
ANALYSIS_SUGESTIONS=["Descreva o sistema composto pelo conjunto de arquivos de código:", 
                     "Gere casos de teste para o sistema composto pelos arquivos a seguir:",
                     "Percorra todos os arquivos de código apresentados e compile a lógica que eles executam. 1. Organize por módulos funcionais; 2.Para cada serviço ou módulo funcional, descreva detalhadamente as tarefas que ele desempenha. 3. Detalhe qual a dependência entre eles e como eles interagem ou não um com o outro."]

def get_iap_user():
    user = request.headers.get('X-Goog-Authenticated-User-Email', "None")
    if user != "None":
        user = user.replace("accounts.google.com:","")
    return user

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
    if clicked_button == "load_context_step_btn":
        prompt = request.form.get("txt_prompt", "").strip()
        context_filename = request.form.get("contexts_slc","")
        if context_filename == "" or request.form["chk_include_ctx"] == "false":
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
        return proceed("loadCodeBucketFolders", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "loadCodeBucketFolders":
        loadCodeBucketFolders()

    elif clicked_button == "generate_unit_tests":
        return proceed("get_blobs_code_unit_test_gen", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "get_blobs_code_unit_test_gen":
        return proceed("generateUnitTests", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code_unit_test_gen())
    elif clicked_button == "generateUnitTests":
        return renderIndex(unitTestFiles = generateUnitTests(get_iap_user(), get_blobs_code_unit_test_gen(), 
                                                             request.form["projects_u_tests_slc"], request.form["model_name"]))
    
    elif clicked_button == "donwload_zip_unit_tests":
        return donwload_zip_file(get_iap_user(), request.form["choosen_project_tests"])

    elif clicked_button == "generate_code_analysis_btn":
        return proceed("get_blobs_to_analyze", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "get_blobs_to_analyze":
        return proceed("generate_code_analysis", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code_for_analysis())
    elif clicked_button == "generate_code_analysis":
        return renderIndex(analysisResult = generate_code_analysis(get_blobs_code_for_analysis(), request.form["txt_code_analysis"], request.form["model_name"]))
    
    return renderIndex()

def renderIndex(page="index.html", any_error="", keep_prompt=True, unitTestFiles=[], analysisResult=""):
    print("METHOD: renderIndex -> " + any_error + " keep_prompt: " + str(keep_prompt))
    global global_contexts
    gc = global_contexts
    activeTab = request.form.get("activeTab", "tabContextGeneration")
    print("activeTab: ", activeTab)
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
        contexts = gc[project]
    choosen_project_tests = request.form.get("projects_u_tests_slc", "")
    if choosen_project_tests == "" and len(global_code_projects) > 0:
        choosen_project_tests = global_code_projects[0]
    print("choosen_project_tests=" + choosen_project_tests + " - global_code_projects=" + str(global_code_projects))
    #print("choosen_model_name="+ choosen_model_name +" project=" + project + " projects=" + str(gc[FOLDERS]) + " contexts=" + str(gc[project]))
    return render_template(page, user=get_iap_user(), activeTab=activeTab, choosen_model_name=choosen_model_name, 
                        prompt_sugestions=PROMPT_SUGESTIONS,
                        txt_prompt=txt_prompt, 
                        chk_include_ctx=request.form.get("chk_include_ctx","true"),
                        project=project, projects=context_projects, contexts=contexts, 
                        loaded_prompts=getLoadedPrompts(),                           
                        projects_code=global_code_projects, choosen_project_tests=choosen_project_tests,
                        unitTestFiles=unitTestFiles,
                        choosen_project_code=request.form.get("projects_code_slc",""),
                        analysis_sugestions=ANALYSIS_SUGESTIONS,
                        txt_code_analysis = request.form.get("txt_code_analysis", ANALYSIS_SUGESTIONS[0]),
                        analysisResult=analysisResult,
                        any_error=any_error)
    
def proceed(target_method="regenerate", bucket=CONTEXTS_BUCKET_NAME, blob_list=[]):
    print("METHOD: proceed" + " target_method: " + target_method)
    if target_method == "regenerate":
        if len(getLoadedPrompts()) == 0:
            return renderIndex(any_error="show_error_no_prompts")
    txt_code_analysis = request.form.get("txt_code_analysis", "")
    if txt_code_analysis == "":
        txt_code_analysis = ANALYSIS_SUGESTIONS[0]
    return render_template("proceed.html", 
                           user=get_iap_user(), 
                           activeTab = request.form.get("activeTab", "tabContextGeneration"),
                           target_method=target_method, model_name=request.form.get("model_name",""), 
                           chk_include_ctx=request.form.get("chk_include_ctx","true"),
                           bucket=bucket, txt_prompt = request.form.get("txt_prompt", ""),
                           choosen_project_tests = request.form.get("projects_u_tests_slc",""),
                           choosen_project_code=request.form.get("projects_code_slc",""),
                           txt_code_analysis = txt_code_analysis,
                           chk_include_txt_midia=request.form.get("chk_include_txt_midia",""),
                           blob_list=blob_list )

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

def loadContextsBucket():
    print("METHOD: loadContextsBucket")
    global global_contexts
    global_contexts = getBucketFilesAndFolders(contextsBucket)

def loadCodeBucketFolders():
    print("METHOD: loadCodeBucketFolders")
    global global_code_projects
    global_code_projects = getBucketFilesAndFolders(codeBucket, False)[FOLDERS] 
    
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
    return [Part.from_uri( uri=uri, mime_type=blob.content_type), prompt]
    #return [prompt, Part.from_uri( uri=uri, mime_type=file_type)]

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

def delete_prompt_step(step_num_str):
    print("METHOD: delete_prompt_step")
    loaded_prompts = getLoadedPrompts()
    step_num = int(step_num_str)
    if step_num <= len(loaded_prompts):
        print(loaded_prompts[step_num-1])
        loaded_prompts.remove(loaded_prompts[step_num-1])
        saveLoadedPrompts(loaded_prompts)

def save_prompts():
    print("METHOD: save_prompts")
    loaded_prompts = getLoadedPrompts()
    return save_cli_file(get_iap_user(), json.dumps(loaded_prompts), request.form["filename_to_save"] , ".json")

def save_results():
    print("METHOD: save_results")
    return save_cli_file(get_iap_user(), request.form["geminiResponse"], request.form["filename_to_save"] ,".txt")

def get_blobs_code_unit_test_gen():
    print("METHOD: get_blobs_code_unit_test_gen")
    return get_code_midia_blobs(request.form["projects_u_tests_slc"], False)

def get_blobs_code_for_analysis():
    return get_code_midia_blobs(request.form["projects_code_slc"] + "/", include_txt_midia=request.form.get("chk_include_txt_midia","") == "on")

if __name__ == "__main__":
    app.run(debug=True)

#considerar o uso:
# https://ai.google.dev/gemini-api/docs/prompting_with_media?lang=python
# https://developers.google.com/drive/api/guides/ref-export-formats