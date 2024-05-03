import os
import ast
from flask import Flask, render_template, request, session, redirect, url_for, send_file
#import base64
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part, FinishReason
import vertexai.preview.generative_models as generative_models
from google.cloud import storage
#from google.auth.transport import requests
#from google.oauth2 import id_token

#PROJECT_ID = os.environ.get("PROJECT_ID")
#REGION = os.environ.get("REGION")
#GAE = os.environ.get("GAE", "TRUE").upper() == "TRUE"
#GAE_APP_ID = os.environ.get("GAE_APP_ID", "default")

# Create a Flask app
app = Flask(__name__)
#vertexai.init(project=PROJECT_ID, location=REGION)
print("RELOADING APPLICATION")
vertexai.init()
storage_client = storage.Client()

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

def get_iap_user():
    return request.headers.get('X-Goog-Authenticated-User-Email', "None")

def loadedPrompts():
    user = get_iap_user()
    if user not in global_loaded_prompts:
        global_loaded_prompts[user] = []
    return global_loaded_prompts[user]

def isPromptRepeated(prompt, filename, gcs_uri):
    loaded_prompts = loadedPrompts()
    if len(loaded_prompts) > 0:
        last_loaded_prompt,_,last_loaded_filename, last_gcs_uri = loaded_prompts[len(loaded_prompts)-1]
        if last_loaded_prompt == prompt and filename == "" and gcs_uri == "":
            return True
        if filename != "" and last_loaded_filename == filename:
            print(last_loaded_filename, " == ", filename)
            return True
        if gcs_uri != "" and last_gcs_uri == gcs_uri:
            return True
    return False

@app.route("/", methods=["GET", "POST"])
def index():
    loaded_prompts = loadedPrompts()
    print("METHOD: index -> " + request.method + " prompts size: " + str(len(loaded_prompts)))
    if request.method == "POST" and "cliked_button" in request.form:
        cliked_button = request.form["cliked_button"]
        print("cliked_button: ", cliked_button)
        if cliked_button == "load_context":
            prompt = request.form.get("prompt", "").strip()
            # Get uploaded file
            text_filename = request.form.get("text_filename","")
            gcs_uri = request.form.get("gcs_uri","")
            print("prompt, text_filename, gcs_uri: ", prompt, text_filename, gcs_uri)
            if prompt == "" and text_filename == "" and gcs_uri == "":
                return renderIndex("show_error_is_empty")
            if text_filename != "" and gcs_uri != "":
                return renderIndex("show_error_mixed_contexts")
            #if prompt == "" and gcs_uri != "":
            #    return renderIndex("show_error_video_needs_request")
            # se o prompt é repetido, é um RE-POST então, ignore
            if isPromptRepeated(prompt, text_filename, gcs_uri):
                return renderIndex("show_error_repeated")
            file_content = request.form.get("textfile_content","")
            loaded_prompts.append((prompt, file_content, text_filename, gcs_uri))
        elif cliked_button == "gcsfile":
            return renderIndex(gcs_uri=request.form["filename"])
        elif cliked_button == "load_gcs_file":
            return proceed("gcsfile")
        elif cliked_button == "generate":
            return proceed("regenerate")
        elif cliked_button == "reset":
            return reset()
        elif cliked_button == "view":
            return view()
        elif cliked_button == "save":
            return save_prompts()
        elif cliked_button == "load_prompts":
            load_prompts(request.form["prompt_json"])
    return renderIndex()

def renderIndex(any_error="", gcs_uri =""):
    print("renderIndex -> " + any_error)
    choosen_model_name = "gemini-1.5-pro-preview-0409"
    if request.method == "POST" and "model_name" in request.form:
        choosen_model_name = request.form["model_name"]
    print("choosen_model_name: ", choosen_model_name)
    loaded_prompts = loadedPrompts()
    return render_template("index.html", user=get_iap_user(), loaded_prompts=loaded_prompts, prompt_len=len(loaded_prompts), choosen_model_name=choosen_model_name, any_error=any_error, gcs_uri=gcs_uri)


@app.route("/gcsfile", methods=["GET", "POST"])
def gcsfile():
    print("METHOD: gcsfile", request.method)
    buckets = []
    last_bck_name = ""
    index = -1
    for bucket in storage_client.list_buckets():
        for blob in bucket.list_blobs():
            if blob.content_type == "video/mp4":
                if last_bck_name != blob.bucket.name:
                    files = []
                    files.append([blob.name, gcsFullName(blob)])
                    buckets.append([blob.bucket.name, files])
                    last_bck_name = blob.bucket.name
                    index += 1
                else:
                    buckets[index][1].append([blob.name, gcsFullName(blob)])
    if len(buckets) == 0:
        return renderIndex(any_error="show_error_no_gcs_file")
    return render_template("gcsfile.html", buckets=buckets, model_name=request.form.get("model_name",""))

def gcsFullName(blob):
    return "gs://" + blob.bucket.name +"/"+ blob.name

@app.route("/proceed", methods=["POST"])
def proceed(method="regenerate"):
    print("METHOD: proceed")
    if method == "regenerate":
        if len(loadedPrompts()) == 0:
            return renderIndex(any_error="show_error_no_prompts")
    return render_template("proceed.html", method=method, model_name=request.form.get("model_name",""))

@app.route("/regenerate", methods=["POST"])
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
        stepResponse = chat.send_message(prompt)
        usage_metadata = stepResponse._raw_response.usage_metadata
        token_consumption.append((usage_metadata.prompt_token_count, usage_metadata.candidates_token_count, usage_metadata.total_token_count))
        geminiResponse.append(stepResponse.candidates[0].content.parts[0].text)
        flatResponse += "*** STEP " + str(index) + " ***\n" + stepResponse.candidates[0].content.parts[0].text +"\n\n"
        # Diferentemente do que eu pensava incialmente, cada mensagem não é estanque:
        # A entrada do passo N+1 inclui os tokens de entrada do passo N+1 mais os passos de saída do passo N
        #tokenConsumptionMessage(usage_metadata, total_token_consumption)
    return render_template("generate.html", loaded_prompts=loaded_prompts, geminiResponse=geminiResponse, flatResponse=flatResponse, model_name=model_name, 
                           token_consumption=token_consumption, total_token_consumption=token_consumption[len(token_consumption)-1])

def tokenConsumptionMessage(usage_metadata, token_consumption):
    token_consumption[0] += usage_metadata.prompt_token_count
    token_consumption[1] += usage_metadata.candidates_token_count
    token_consumption[2] += usage_metadata.total_token_count
    return 

def prepare_prompt(promptItem):
    print("METHOD: prepare_prompt")
    prompt, contexto, filename , gcs_uri = promptItem
    print("prompt:", prompt, "filename:", filename, "video;", gcs_uri)
    # verificar se a string "prompt" contem a substring "{xxxx}"
    if contexto == "" and gcs_uri == "":
        return prompt
    if prompt == "" and gcs_uri == "":
        return contexto
    # verificar se a string "prompt" contem a substring "{contexto}"'
    if gcs_uri == "":
        if not "{contexto}" in prompt:
            return prompt + f" \"{contexto}\""
        else: 
            return (prompt.replace("{contexto}", f" \"{contexto}\""))
    #if "{contexto}" in prompt: necessário ?
    #    return (prompt.replace("{contexto}", f" \"{contexto}\""))    
    #return ["\"\"" + prompt + "\"\"" , Part.from_uri(mime_type="video/mp4", uri="gs://"+ gcs_uri)]
    return [prompt, Part.from_uri(mime_type="video/mp4", uri=gcs_uri)]


#@app.route("/reset", methods=["POST"])
def reset():
    print("METHOD: reset")
    loadedPrompts().clear()
    print("Contexto limpo!")
    return renderIndex("")

def view():
    print("METHOD: view")
    prompts = []
    for promptItem in loadedPrompts():
        prompts.append(prepare_prompt(promptItem))
    return render_template("view_prompts.html", prompts=prompts)

def load_prompts(prompts_json):
    print("METHOD: load_prompts")
    print(len(prompts_json))
    loaded_prompts = loadedPrompts()
    prompts_from_file = json.loads(prompts_json)
    loaded_prompts.clear()
    for prompt in prompts_from_file:
        loaded_prompts.append((prompt[0], prompt[1], prompt[2], prompt[3]))

def save_prompts():
    print("METHOD: save_prompts")
    loaded_prompts = loadedPrompts()
    #if len(loaded_prompts) == 0:
    #    return renderIndex("show_error_no_prompts_to_save")
    prompts_filename = request.form["prompts_filename"] + ".json"
    print(prompts_filename)
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
