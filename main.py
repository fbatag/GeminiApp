import datetime, os
from flask import Flask, request, render_template
#from flask import session, redirect, url_for
import vertexai
from google.appengine.api import wrap_wsgi_app

#from google.appengine.ext import db, ndb
from gemapp.content_gen import IS_GAE_ENV_STD, CONTEXTS_BUCKET_NAME, load_prompts, loadContextsBucket, get_global_contexts, delete_prompt_step, deleteContext, view_prompts
from gemapp.content_gen import create_project, isPromptRepeated, getLoadedPrompts, saveLoadedPrompts, generate, save_results, save_prompts_to_file
from gemapp.content_gen import uploadContext, contextsBucket

from gemapp.utils import FOLDERS, get_iap_user, getBucketFilesAndFolders, donwload_zip_file, excludeBlobFolder
from gemapp.code_analysis import CODE_BUCKET_NAME, codeBucket, get_code_media_blobs, generateCode, analizeCode, split_string_by_lines

print("(RE)LOADING APPLICATION")
local_cred_file = os.environ.get("HOME") +"/.config/gcloud/gemini-app-sa.json"
print(local_cred_file)
app = Flask(__name__)

if IS_GAE_ENV_STD:
    app.wsgi_app = wrap_wsgi_app(app.wsgi_app)

vertexai.init()
global_code_projects =[]

PROMPT_SUGESTIONS=["", "Crie casos de teste a partir do sistema descrito no video:", "Crie casos de teste a partir do sistema descrito no documento:"]
ANALYSIS_SUGESTIONS=["Descreva o sistema composto pelo conjunto de arquivos de código:", 
    "Gere casos de teste para o sistema composto pelos arquivos a seguir:",
    "Percorra todos os arquivos de código apresentados e compile a lógica que eles executam. 1. Organize por módulos funcionais; 2.Para cada serviço ou módulo funcional, descreva detalhadamente as tarefas que ele desempenha. 3. Detalhe qual a dependência entre eles e como eles interagem ou não um com o outro.",
    "Gere testes unitários para este código","Converta o código para Java", "Converta o código para Python", "Converta o código para C#", "Converta o código para JavaScript"]

from google import auth
credentials, project_id = auth.default()
from google.oauth2 import service_account

def get_user_version_info():
    return "User: " + get_iap_user() + " -  Version: 1.2.1"

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
                                    credentials=service_account.Credentials.from_service_account_file(local_cred_file),
                                    #credentials=credentials,
                                    headers={"X-Goog-Content-Length-Range": "1,5000000000", 'Content-Type': filetype})
    else:
        print("CREDENTIALS")
        print(credentials.service_account_email)
        #if credentials.token is None:
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
        if context_filename == "" or request.form["include_file_context"] == "false":
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

    elif clicked_button == "loadContextsAndCodeBuckets":
        loadContextsBucket()
        loadCodeBucketFolders()

    # Code/Context management for Analysis/Generation
    # Adding is done in JS in codeProjectFolderSelect.addEventListener
    # Update UI
    elif clicked_button == "update_code_files_btn":
        return proceed("loadCodeBucketFolders", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "loadCodeBucketFolders":
        loadCodeBucketFolders()
    # Excluiding a Project
    elif clicked_button == "exclude_code_files_btn":
        return proceed("exclude_code_files", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "exclude_code_files":
        folder = request.form["projects_code_slc"]
        print(f"deleting GCS code bucket ({CODE_BUCKET_NAME}) folder ({folder})")
        excludeBlobFolder(codeBucket, folder)
        loadCodeBucketFolders()

    # list buttons
    elif clicked_button == "list_code_btn":
        return renderIndex(analysisResult = list_blobs_code(get_blobs_code()))

    elif clicked_button == "list_long_code_btn":
        return renderIndex(analysisResult = list_blobs_code_with_chunks(get_blobs_code_only_txt()))

    # Code/Context Analysis
    elif clicked_button == "analize_code_btn":
        return proceed("get_blobs_to_analyze", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "get_blobs_to_analyze":
        return proceed("analizeCode", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code())
    elif clicked_button == "analizeCode":
        return renderIndex(analysisResult = analizeCode(get_blobs_code(), request.form["txt_prompt_analysis"], request.form["model_name"]))

    # Code/Context Generation
    elif clicked_button == "generate_code_btn":
        return proceed("get_blobs_code", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "get_blobs_code":
        return proceed("generateCode", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code())
    elif clicked_button == "generateCode":
        return renderIndex(codeGeneratedFiles = generateCode(get_blobs_code(), request.form["choosen_project_code"], 
                                                request.form["txt_prompt_analysis"], request.form["model_name"]))
    elif clicked_button == "donwload_zip_generated_files":
        return donwload_zip_file(request.form["choosen_project_code"])
    
    # Code/Context Generation - long output more than 8k tokens
    elif clicked_button == "generate_code_long_output_btn":
        return proceed("get_blobs_code_to_long_output", bucket=CODE_BUCKET_NAME )
    elif clicked_button == "get_blobs_code_to_long_output":
        return proceed("generateCodeLongOutput", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code_only_txt())
    elif clicked_button == "generateCodeLongOutput":
        return renderIndex(codeGeneratedFiles = generateCode(get_blobs_code_only_txt(), request.form["choosen_project_code"], 
                                                request.form["txt_prompt_analysis"], request.form["model_name"], int(request.form.get("lines_chunck_size", "100"))))
    elif clicked_button == "donwload_zip_generated_files":
        return donwload_zip_file(request.form["choosen_project_code"])
    
    return renderIndex()

def renderIndex(page="index.html", any_error="", keep_prompt=True, codeGeneratedFiles=[], analysisResult=""):
    print("METHOD: renderIndex -> " + any_error + " keep_prompt: " + str(keep_prompt))
    gc = get_global_contexts()
    activeTab = request.form.get("activeTab", "tabContextGeneration")
    print("activeTab: ", activeTab)
    if not FOLDERS in gc:
        return proceed("loadContextsAndCodeBuckets")
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
    choosen_project_code = request.form.get("choosen_project_code", "")
    if not choosen_project_code in global_code_projects and len(global_code_projects) > 0:
        choosen_project_code = global_code_projects[0]
    print("choosen_project_code=" + choosen_project_code + " - global_code_projects=" + str(global_code_projects))

    return render_template(page, user_version_info=get_user_version_info(), activeTab=activeTab, choosen_model_name=choosen_model_name, 
                        prompt_sugestions=PROMPT_SUGESTIONS,
                        txt_prompt=txt_prompt, 
                        include_file_context=request.form.get("include_file_context","true"),
                        project=project, projects=context_projects, contexts=contexts, 
                        loaded_prompts=getLoadedPrompts(),
                        projects_code=global_code_projects,
                        codeGeneratedFiles=codeGeneratedFiles,
                        choosen_project_code=choosen_project_code,
                        analysis_sugestions=ANALYSIS_SUGESTIONS,
                        txt_prompt_analysis = request.form.get("txt_prompt_analysis", ANALYSIS_SUGESTIONS[0]),
                        include_media_file=request.form.get("include_media_file","true"),
                        analysisResult=analysisResult,
                        lines_chunck_size=request.form.get("lines_chunck_size", "100"),
                        any_error=any_error,
                        code_bucket_name=CODE_BUCKET_NAME)
    
def proceed(target_method="regenerate", bucket=CONTEXTS_BUCKET_NAME, blob_list=[]):
    print("METHOD: proceed" + " target_method: " + target_method)
    if target_method == "regenerate":
        if len(getLoadedPrompts()) == 0:
            return renderIndex(any_error="show_error_no_prompts")
    return render_template("proceed.html", 
                           user_version_info=get_user_version_info(), 
                           activeTab = request.form.get("activeTab", "tabContextGeneration"),
                           target_method=target_method, model_name=request.form.get("model_name",""), 
                           include_file_context=request.form.get("include_file_context","true"),
                           txt_prompt = request.form.get("txt_prompt", ""),
                           choosen_project_code=request.form.get("choosen_project_code",""),
                           txt_prompt_analysis = request.form.get("txt_prompt_analysis", ""),
                           include_media_file=request.form.get("include_media_file","true"),
                           bucket=bucket,
                           blob_list=blob_list,
                           lines_chunck_size=request.form.get("lines_chunck_size", "100"))

def loadCodeBucketFolders():
    print("METHOD: loadCodeBucketFolders")
    global global_code_projects
    global_code_projects = getBucketFilesAndFolders(codeBucket, False)[FOLDERS] 

def list_blobs_code(blob_list):
    msg = "Arquivos que serão considerados com a seleção atual:\n\n"
    for blob in blob_list:
        msg += blob.name + "\n"
    return msg

def list_blobs_code_with_chunks(blob_list):
    msg = "Arquivos que serão considerados com a seleção atual:\n\n"
    lines_chunck_size = request.form.get("lines_chunck_size", "100")
    for blob in blob_list:
        msg += blob.name + " -> processado em " + str(len(split_string_by_lines(blob, int(lines_chunck_size)))) + " partes de " + lines_chunck_size + " linhas cada.\n"
    msg+= "\n\nVerifique o tamanho da linha e o tamanho da saída esperada. Considere uma estimativa de quantas linhas resultantes serão para cada parte e seu tamanho em bytes. Divida por 4 para obter uma média de tokens. Como o limite de saída por chamada/parte é hoje de 8k tokens, considere esse limite no seu cálculo de quantidade de linhas."
    return msg

def get_blobs_code_only_txt():
    return get_code_media_blobs(request.form["choosen_project_code"] + "/", False)

def get_blobs_code():
    return get_code_media_blobs(request.form["choosen_project_code"] + "/", include_txt_media=request.form.get("include_media_file","false") == "true")

if __name__ == "__main__":
    app.run(debug=True)

#considerar o uso:
# https://ai.google.dev/gemini-api/docs/prompting_with_media?lang=python
# https://developers.google.com/drive/api/guides/ref-export-formats