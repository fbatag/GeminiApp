export PROJECT_ID=<PROJECT_ID>
export REGION=<REGION> # deve ser uma região que onde o Gemini esteja deploiado - us-central1 southamerica-east1 us-east1 us-east4
export SUPPORT_EMAIL=<mail do user executando estes comandos>
export USER_EMAIL=<user do dominio - que tem acesso ao console GCP>
export USER_EMAIL_DEPLOY=<usesr que continuará fazendo deploy de novas versões>

gcloud iam service-accounts create gemini-app-sa \
--display-name "Gemini App Generator Service Account" \
--project $PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/storage.admin

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/aiplatform.user

gcloud services enable storage-component.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable appengine.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable iap.googleapis.com 

gcloud app create --project=$PROJECT_ID --region=$REGION \
--service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com

gcloud app deploy --project=$PROJECT_ID --quiet

gcloud iap oauth-brands create --application_title=GeminiApp --support_email=$SUPPORT_EMAIL
gcloud iap oauth-clients create BRAND --display_name=GeminiApp
gcloud iap web enable --resource-type=app-engine 
    
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL" --role="roles/iap.httpsResourceAccessor"


# o trecho a seguir é somente se o usuário que continuara atualziando as versões é diferente e terá menos permissões
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL_DEPLOY" --role="roles/appengine.appAdmin"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL_DEPLOY" --role="roles/cloudbuild.builds.editor"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL_DEPLOY" --role="roles/storage.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL_DEPLOY" --role="roles/viewer"
gcloud iam service-accounts add-iam-policy-binding gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --member="user:$USER_EMAIL_DEPLOY" \
    --role="roles/iam.serviceAccountAdmin"

