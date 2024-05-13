import os
from flask import Flask, render_template, request, session, redirect, url_for, send_file
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
import vertexai.preview.generative_models as generative_models
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
print("CONTEXTS_BUCKET_NAME: " + CONTEXTS_BUCKET_NAME)

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

# ATENÇÃO: Apesar de existirem esses valores no Enum, o modelo NÃO aceita esses parãmetros
#safety_settings = {
#    HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
#    generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_NONE,
#    generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
#    generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_NONE,
#    generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
#}

# Inicializa o array para armazenar os dados
global_loaded_prompts = dict()
global_contexts = dict()
FOLDERS =  "!<FOLDERS>!"


def get_iap_user():
    return request.headers.get('X-Goog-Authenticated-User-Email', "None")

def loadedPrompts():
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
    user = get_iap_user()
    if IS_GAE_ENV_STD:
        memcache.set(user, json.dumps(loadedPrompts))
        #memcache.set(user, db.model_to_protobuf(loadedPrompts))
    global_loaded_prompts[user] = loadedPrompts

def isPromptRepeated(prompt, project_name, filename):
    loaded_prompts = loadedPrompts()
    if len(loaded_prompts) > 0:
        #last_loaded_prompt, last_loaded_filename = loaded_prompts[len(loaded_prompts)-1]
        last_loaded_prompt, last_project, last_loaded_filename = loaded_prompts[-1]
        if last_loaded_prompt == prompt and last_project == project_name and filename == last_loaded_filename:
            return True
    return False

@app.route("/", methods=["GET", "POST"])
def index():
    loaded_prompts = loadedPrompts()
    print("METHOD: index -> " + request.method + " prompts size: " + str(len(loaded_prompts)))
    print(request.form.items)
    clicked_button = request.form.get('clicked_button', "NOT_FOUND")
    print("clicked_button: ", clicked_button)
    if clicked_button == "load_context_step_btn":
        prompt = request.form.get("prompt", "").strip()
        # Get uploaded file
        project_name = request.form.get("projects_slc","")
        context_filename = request.form.get("contexts_slc","")
        if prompt == "":
            return renderIndex(any_error="show_error_is_empty")
        if isPromptRepeated(prompt, project_name, context_filename):
            return renderIndex(any_error="show_error_repeated")
        loaded_prompts.append((prompt, project_name, context_filename))
        saveLoadedPrompts(loaded_prompts)
    elif clicked_button == "update_contexts_btn": 
        return proceed("loadContextsBucket")
    #elif clicked_button == "ctx_return_btn": 
    #    return proceed("loadContextsBucket")
    elif clicked_button == "loadContextsBucket":
        loadContextsBucket()
        return renderIndex()
    elif clicked_button == "manage_contexts_btn":
        return renderIndex("context.html")
    elif clicked_button == "upload_context_btn":
        uploadContext()
        loadContextsBucket()
        return renderIndex("context.html")
    elif clicked_button == "create_prj_btn":
        create_project(request.form["new_prj_name"])
        loadContextsBucket()
        return renderIndex("context.html")
    elif clicked_button == "projects_slc":
        return renderIndex()
    elif clicked_button == "generate":
        return proceed("regenerate")
    elif clicked_button == "regenerate":
        return generate()
    elif clicked_button == "reset":
        return reset()
    elif clicked_button == "view":
        return view()
    elif clicked_button == "save":
        return save_prompts()
    elif clicked_button == "load_prompts_btn":
        load_prompts(request.form["prompt_history_json"])
    return renderIndex()

def renderIndex(page="index.html", any_error=""):
    print("METHOD: renderIndex -> " + any_error)
    global global_contexts
    gc = global_contexts
    if not FOLDERS in gc:
        return proceed("loadContextsBucket")
    project = request.form.get("projects_slc", "")
    choosen_model_name = request.form.get("model_name", "gemini-1.5-pro-preview-0409")
    if project == "" and len(gc[FOLDERS]) > 0:
        project = gc[FOLDERS][0]
    if project == "" or len(gc[FOLDERS]) == 0:
        print("EMPTY ** choosen_model_name="+ choosen_model_name +" project=" + project + " projects=[] contexts=[]")
        return render_template(page, user=get_iap_user(), loaded_prompts=loadedPrompts(), choosen_model_name=choosen_model_name, project=project, projects=[], contexts=[], any_error=any_error)
    print("choosen_model_name="+ choosen_model_name +" project=" + project + " projects=" + str(gc[FOLDERS]) + " contexts=" + str(gc[project]))
    return render_template(page, user=get_iap_user(), loaded_prompts=loadedPrompts(), choosen_model_name=choosen_model_name, project=project, projects=gc[FOLDERS], contexts=gc[project], any_error=any_error)

def getBucket():
    storage_client = storage.Client()
    # Cria um bucket se ele não existir
    bucket = storage_client.bucket(CONTEXTS_BUCKET_NAME)
    if not bucket.exists():
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        #bucket.create(location=REGION)
        bucket.create()
        print("Bucket {} created".format(CONTEXTS_BUCKET_NAME))
    return bucket        

def create_project(new_prj_name):
    print("METHOD: create_project", new_prj_name)
    bucket = getBucket()
    blob = bucket.blob(new_prj_name + "/")
    blob.upload_from_string("")
    
def uploadContext():
    print("METHOD: uploadContext", request.method)
    project = request.form["projects_slc"]
    file = request.files["load_context_file"]
    if file:
        bucket = getBucket()
        # Faz o upload do arquivo para o bucket
        blob = bucket.blob(project + "/" + file.filename)
        print(file.content_type)
        #blob.upload_from_file(file, content_type='video/mp4')
        blob.upload_from_file(file, content_type=file.content_type)

def loadContextsBucket():
    print("METHOD: loadContextsBucket")
    bucket = getBucket()
    blobs = bucket.list_blobs()
    gc = dict()
    projects = []
    for blob in blobs:
        # Extract folder name by splitting on '/' and taking everything but the last part
        parts = blob.name.split('/')
        if len(parts) > 1:
            folder_name = '/'.join(parts[:-1])
        else:
            folder_name = "/"  # Root level
        # Add blob to the corresponding folder list
        if not folder_name in gc:
            gc[folder_name] = []
            projects.append(folder_name)
        if parts[-1]:
            gc[folder_name].append(parts[-1])
    gc[FOLDERS]  = projects
    global global_contexts
    global_contexts = gc


@app.route("/proceed", methods=["POST"])
def proceed(method="regenerate"):
    print("METHOD: proceed")
    if method == "regenerate":
        if len(loadedPrompts()) == 0:
            return renderIndex(any_error="show_error_no_prompts")
    return render_template("proceed.html", method=method, model_name=request.form.get("model_name",""), bucket=CONTEXTS_BUCKET_NAME)

#@app.route("/regenerate", methods=["POST"])
def generate():
    print("METHOD: regenerate")
    model_name = request.form["model_name"]
    print("Model: " + model_name)
    model = GenerativeModel(model_name, generation_config=generation_config, safety_settings=safety_settings)
    chat = model.start_chat()
    
    token_consumption = []
    #total_token_consumption = [0,0,0]
    loaded_prompts = loadedPrompts()
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

def prepare_prompt(promptItem):
    print("METHOD: prepare_prompt")
    prompt, project_name, filename = promptItem
    print("prompt: ", prompt, " - project: ", project_name, " - filename: ", filename)
    #if filename != "":
        #if not "{contexto}" in prompt:
            #return prompt + f" \"{filename}\""
        #else: 
            #return (prompt.replace("{contexto}", f" \"{filename}\""))
    uri="gs://" + CONTEXTS_BUCKET_NAME +"/"+ project_name + "/" + filename
    file_type = getFileType(filename)
    #print("file_type: ", file_type)
    #print("uri: ", uri)
    return [prompt, Part.from_uri(mime_type=file_type, uri=uri)]

def getFileType(filename):
    print("METHOD: getFileType")
    file_type = filename.split(".").pop()
    if  file_type == "mp4":
        return "video/mp4"
    elif file_type == "pdf":
        return "application/pdf"
    return "text/plain"

#@app.route("/reset", methods=["POST"])
def reset():
    print("METHOD: reset")
    saveLoadedPrompts([])
    print("Contexto limpo!")
    return renderIndex()

def view():
    print("METHOD: view")
    prompts = []
    for promptItem in loadedPrompts():
        prompts.append(prepare_prompt(promptItem))
    return render_template("view_prompts.html", prompts=prompts)

def load_prompts(prompts_json):
    print("METHOD: load_prompts")
    print("Loaded prompt size:" + str(len(prompts_json)))
    saveLoadedPrompts(json.loads(prompts_json))

def save_prompts():
    print("METHOD: save_prompts")
    loaded_prompts = loadedPrompts()
    prompts_filename = request.form["prompts_filename"] + ".json"
    # Converte a lista "loaded_prompts" para um objeto JSON
    json_data = json.dumps(loaded_prompts)
    prompts_json_path = os.path.join(tempDir(), "prompts_file.json")
    with open(prompts_json_path, "w") as f:
        f.write(json_data)
    #return send_file(prompts_json_path, as_attachment=True, download_name="prompts_file.json")
    return send_file(prompts_json_path, as_attachment=True, download_name=prompts_filename)

@app.route("/save", methods=["POST"])
def save_results():
    print("METHOD: save_results")
    results_filename = request.form["results_filename"] + ".txt"
    print(results_filename)
    file_path = os.path.join(tempDir(), "results_file.txt")
    geminiResponse = request.form["geminiResponse"]
    with open(file_path, "w") as arquivo:
        arquivo.write(geminiResponse)
    return send_file(file_path, as_attachment=True, download_name=results_filename)

def tempDir():
    temp_dir = "/tmp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return temp_dir

def clearDir():
    temp_dir = tempDir()
    #files = os.listdir(temp_dir)
    #for file in files:
    #    os.remove(os.path.join(temp_dir, file))

if __name__ == "__main__":
    app.run(debug=True)
