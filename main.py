from flask import Flask, request, render_template
#from flask import session, redirect, url_for
import vertexai
from google.appengine.api import wrap_wsgi_app

#from google.appengine.ext import db, ndb
from gemapp.content_gen import IS_GAE_ENV_STD, CONTEXTS_BUCKET_NAME, load_prompts, loadContextsBucket, get_global_contexts, delete_prompt_step, deleteContext, view_prompts
from gemapp.content_gen import create_project, isPromptRepeated, getLoadedPrompts, saveLoadedPrompts, uploadContext, generate, save_results, save_prompts_to_file

from gemapp.utils import FOLDERS, get_iap_user, getBucketFilesAndFolders, donwload_zip_file
from gemapp.code_analysis import CODE_BUCKET_NAME, codeBucket, get_code_midia_blobs, generateUnitTests, generate_code_analysis

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

    elif clicked_button == "generate_unit_tests":
        return proceed("get_blobs_code_unit_test_gen", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "get_blobs_code_unit_test_gen":
        return proceed("generateUnitTests", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code_unit_test_gen())
    elif clicked_button == "generateUnitTests":
        return renderIndex(unitTestFiles = generateUnitTests(get_blobs_code_unit_test_gen(), request.form["projects_u_tests_slc"], request.form["model_name"]))
    
    elif clicked_button == "donwload_zip_unit_tests":
        return donwload_zip_file(request.form["choosen_project_tests"])

    elif clicked_button == "generate_code_analysis_btn":
        return proceed("get_blobs_to_analyze", bucket=CODE_BUCKET_NAME)
    elif clicked_button == "get_blobs_to_analyze":
        return proceed("generate_code_analysis", bucket=CODE_BUCKET_NAME, blob_list=get_blobs_code_for_analysis())
    elif clicked_button == "generate_code_analysis":
        return renderIndex(analysisResult = generate_code_analysis(get_blobs_code_for_analysis(), request.form["txt_code_analysis"], request.form["model_name"]))
    
    return renderIndex()

def renderIndex(page="index.html", any_error="", keep_prompt=True, unitTestFiles=[], analysisResult=""):
    print("METHOD: renderIndex -> " + any_error + " keep_prompt: " + str(keep_prompt))
    gc = get_global_contexts()
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

def loadCodeBucketFolders():
    print("METHOD: loadCodeBucketFolders")
    global global_code_projects
    global_code_projects = getBucketFilesAndFolders(codeBucket, False)[FOLDERS] 
    
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