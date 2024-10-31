import datetime
from flask import Flask, request, render_template
#from flask import session, redirect, url_for
import vertexai
from google.appengine.api import wrap_wsgi_app

#from google.appengine.ext import db, ndb
from gemapp.content_gen import IS_GAE_ENV_STD, CONTEXTS_BUCKET_NAME, load_prompts, loadContextsBucket, get_global_contexts, delete_prompt_step, deleteContext, view_prompts
from gemapp.content_gen import create_project, isPromptRepeated, getLoadedPrompts, saveLoadedPrompts, generate, save_results, save_prompts_to_file
from gemapp.content_gen import uploadContext, contextsBucket

from gemapp.utils import FOLDERS, get_iap_user, getBucketFilesAndFolders, donwload_zip_file, excludeBlobFolder
from gemapp.code_analysis import CODE_BUCKET_NAME, codeBucket, get_code_midia_blobs, generateCode, generate_code_analysis

print("(RE)LOADING APPLICATION")
app = Flask(__name__)

if IS_GAE_ENV_STD:
    app.wsgi_app = wrap_wsgi_app(app.wsgi_app)

vertexai.init()
global_code_projects =[]

PROMPT_SUGESTIONS=["", "Crie casos de teste a partir do sistema descrito no video:", "Crie casos de teste a partir do sistema descrito no documento:"]
ANALYSIS_SUGESTIONS=["Descreva o sistema composto pelo conjunto de arquivos de código:", 
                     "Gere casos de teste para o sistema composto pelos arquivos a seguir:",
                     "Percorra todos os arquivos de código apresentados e compile a lógica que eles executam. 1. Organize por módulos funcionais; 2.Para cada serviço ou módulo funcional, descreva detalhadamente as tarefas que ele desempenha. 3. Detalhe qual a dependência entre eles e como eles interagem ou não um com o outro."]
CODE_GENERATION_SUGESTIONS=["Gere testes unitários para este código","Converta o código para Java", "Converta o código para Python", "Converta o código para C#", "Converta o código para JavaScript"]

from google import auth
credentials, project_id = auth.default()
from google.oauth2 import service_account

def get_user_version_info():
    return "User: " + get_iap_user() + " -  Version: 1.1.0"
    return

@app.route("/getSignedUrl", methods=["GET"])
def getSignedUrl():
    print("METHOD: getSignedUrl")
    print(request.args)
    dest_bucket = request.args.get("dest_bucket")
    object_destination = request.args.get("object_destination")
    filetype = request.args.get("filetype")
    if dest_bucket == "code":
        return getSignedUrlParam(codeBucket, object_destination, filetype)
    return getSignedUrlParam(contextsBucket, object_destination, filetype)

def getSignedUrlParam(dest_bucket, object_destination, filetype):
    blob = dest_bucket.blob(object_destination)
    expiration=datetime.timedelta(minutes=15)

    print('Content-Type: '+  filetype)
    if request.url_root == 'http://127.0.0.1:5000/':
        print("RUNNING LOCAL")
        signeUrl = blob.generate_signed_url(method='PUT', version="v4", expiration=expiration, content_type=filetype, 
                                    credentials=service_account.Credentials.from_service_account_file("../sa.json"),
                                    headers={"X-Goog-Content-Length-Range": "1,5000000000", 'Content-Type': filetype})
    else:
        print("CREDENTIALS")
        print(credentials.service_account_email)
        if credentials.token is None:
            credentials.refresh(auth.transport.requests.Request())
        print(credentials.token)
        signeUrl = blob.generate_signed_url(method='PUT', version="v4", expiration=expiration, content_type=filetype, 
                                    service_account_email=credentials.service_account_email, access_token=credentials.token,
                                    headers={"X-Goog-Content-Length-Range": "1,5000000000", 'Content-Type': filetype})
        #except Exception as e:
        #    print(e)
    #print(signeUrl)
    return signeUrl


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
        return generate(request.form["model_name"])
    elif clicked_button == "reset_prompts":
        saveLoadedPrompts([])
        print("Contexto limpo!")
        return renderIndex()
    elif clicked_button == "view_prompts":
        return view_prompts()
    elif clicked_button == "save_prompts":
        return save_prompts_to_file()
    elif clicked_button == "load_prompts_btn":
        return renderIndex(any_error=load_prompts(request.form["prompt_history_json"]))
    # generate.html buttons
    elif clicked_button == "save_result_btn":
        return save_results()
    elif clicked_button == "update_code_files_btn":
        return proceed("loadCodeBucketFolders", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "loadCodeBucketFolders":
        loadCodeBucketFolders()

    elif clicked_button == "generate_code":
        return proceed("get_blobs_code_generation", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "get_blobs_code_generation":
        return proceed("generateCode", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code_generation())
    elif clicked_button == "generateCode":
        return renderIndex(codeGenerationFiles = generateCode(get_blobs_code_generation(), request.form["projects_code_gen_slc"], request.form["txt_code_generation"], request.form["model_name"]))
    
    elif clicked_button == "donwload_zip_generated_files":
        return donwload_zip_file(request.form["choosen_project_code_generation"])

    elif clicked_button == "generate_code_analysis_btn":
        return proceed("get_blobs_to_analyze", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "get_blobs_to_analyze":
        return proceed("generate_code_analysis", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code_for_analysis())
    elif clicked_button == "generate_code_analysis":
        return renderIndex(analysisResult = generate_code_analysis(get_blobs_code_for_analysis(), request.form["txt_code_analysis"], request.form["model_name"]))
    
    elif clicked_button == "exclude_code_files_btn":
        return proceed("exclude_code_files", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "exclude_code_files":
        folder = request.form["projects_code_slc"]
        print(f"deleting GCS code bucket ({CODE_BUCKET_NAME}) folder ({folder})")
        excludeBlobFolder(codeBucket, folder)
        loadCodeBucketFolders()
    
    return renderIndex()

def renderIndex(page="index.html", any_error="", keep_prompt=True, codeGenerationFiles=[], analysisResult=""):
    print("METHOD: renderIndex -> " + any_error + " keep_prompt: " + str(keep_prompt))
    gc = get_global_contexts()
    activeTab = request.form.get("activeTab", "tabContextGeneration")
    print("activeTab: ", activeTab)
    if not FOLDERS in gc:
        return proceed("loadContextsBucket")
    choosen_model_name = request.form.get("model_name", "gemini-1.5-flash-002")
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
    choosen_project_code_generation = request.form.get("projects_code_gen_slc", "")
    if choosen_project_code_generation == "" and len(global_code_projects) > 0:
        choosen_project_code_generation = global_code_projects[0]
    print("choosen_project_code_generation=" + choosen_project_code_generation + " - global_code_projects=" + str(global_code_projects))

    return render_template(page, user_version_info=get_user_version_info(), activeTab=activeTab, choosen_model_name=choosen_model_name, 
                        prompt_sugestions=PROMPT_SUGESTIONS,
                        txt_prompt=txt_prompt, 
                        chk_include_ctx=request.form.get("chk_include_ctx","true"),
                        project=project, projects=context_projects, contexts=contexts, 
                        loaded_prompts=getLoadedPrompts(),                           
                        projects_code=global_code_projects, choosen_project_code_generation=choosen_project_code_generation,
                        codeGenerationFiles=codeGenerationFiles,
                        choosen_project_code=request.form.get("projects_code_slc",""),
                        analysis_sugestions=ANALYSIS_SUGESTIONS,
                        txt_code_analysis = request.form.get("txt_code_analysis", ANALYSIS_SUGESTIONS[0]),
                        code_gen_sugestions=CODE_GENERATION_SUGESTIONS,
                        txt_code_generation = request.form.get("txt_code_generation", CODE_GENERATION_SUGESTIONS[0]),
                        analysisResult=analysisResult,
                        any_error=any_error,
                        code_bucket_name=CODE_BUCKET_NAME)
    
def proceed(target_method="regenerate", bucket=CONTEXTS_BUCKET_NAME, blob_list=[]):
    print("METHOD: proceed" + " target_method: " + target_method)
    if target_method == "regenerate":
        if len(getLoadedPrompts()) == 0:
            return renderIndex(any_error="show_error_no_prompts")
    txt_code_analysis = request.form.get("txt_code_analysis", "")
    if txt_code_analysis == "":
        txt_code_analysis = ANALYSIS_SUGESTIONS[0]
    txt_code_generation = request.form.get("txt_code_generation", "")
    if txt_code_generation == "":
        txt_code_generation = CODE_GENERATION_SUGESTIONS[0]
    return render_template("proceed.html", 
                           user_version_info=get_user_version_info(), 
                           activeTab = request.form.get("activeTab", "tabContextGeneration"),
                           target_method=target_method, model_name=request.form.get("model_name",""), 
                           chk_include_ctx=request.form.get("chk_include_ctx","true"),
                           bucket=bucket, txt_prompt = request.form.get("txt_prompt", ""),
                           choosen_project_code_generation = request.form.get("projects_code_gen_slc",""),
                           choosen_project_code=request.form.get("projects_code_slc",""),
                           txt_code_analysis = txt_code_analysis,
                           txt_code_generation=txt_code_generation,
                           chk_include_txt_midia=request.form.get("chk_include_txt_midia",""),
                           blob_list=blob_list)

def loadCodeBucketFolders():
    print("METHOD: loadCodeBucketFolders")
    global global_code_projects
    global_code_projects = getBucketFilesAndFolders(codeBucket, False)[FOLDERS] 
    
def get_blobs_code_generation():
    print("METHOD: get_blobs_code_generation")
    return get_code_midia_blobs(request.form["projects_code_gen_slc"], False)

def get_blobs_code_for_analysis():
    return get_code_midia_blobs(request.form["projects_code_slc"] + "/", include_txt_midia=request.form.get("chk_include_txt_midia","") == "on")

if __name__ == "__main__":
    app.run(debug=True)

#considerar o uso:
# https://ai.google.dev/gemini-api/docs/prompting_with_media?lang=python
# https://developers.google.com/drive/api/guides/ref-export-formats