export PROJECT_ID=$(gcloud config get project)
echo $PROJECT_ID
export REGION=southamerica-east1
export SUPPORT_EMAIL=dev@fbatagin.altostrat.com
export USER_GROUP=gcp-devops@fbatagin.altostrat.com
export DEPLOY_GROUP=gcp-devops@fbatagin.altostrat.com

export APP_NAME=gemini-app
export SERVICE_NAME=$APP_NAME-ui
export SERVICE_ACCOUNT=$APP_NAME-sa

gcloud services enable storage-component.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable appengine.googleapis.com
gcloud services enable cloudbuild.googleapis.com # para o Cloud Run
gcloud services enable iap.googleapis.com 
#gcloud services enable vision.googleapis.com # para covnersão de pdf em texto - não usado atualmente

gsutil mb -b on -l $REGION gs://gen-ai-app-contexts-$PROJECT_ID
gsutil lifecycle set bucket_lifecycle.json gs://gen-ai-app-contexts-$PROJECT_ID
gcloud storage buckets update gs://gen-ai-app-contexts-$PROJECT_ID --cors-file=bucket-cors.json
gcloud storage buckets describe gs://gen-ai-app-contexts-$PROJECT_ID --format="default(cors_config)" # Verirficar se acatou

gsutil mb -b on -l $REGION gs://gen-ai-app-code-$PROJECT_ID
gsutil lifecycle set bucket_lifecycle.json gs://gen-ai-app-code-$PROJECT_ID
gcloud storage buckets update gs://gen-ai-app-code-$PROJECT_ID --cors-file=bucket-cors.json
gcloud storage buckets describe gs://gen-ai-app-code-$PROJECT_ID --format="default(cors_config)" # Verirficar se acatou


gcloud iam service-accounts create $SERVICE_ACCOUNT \
--display-name "Gemini App Generator Service Account" \
--project $PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/aiplatform.user

gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-contexts-$PROJECT_ID \
--member serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/storage.objectUser --project=$PROJECT_ID

gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-code-$PROJECT_ID \
--member serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/storage.objectUser --project=$PROJECT_ID

# Para funcionar o upload usando SignedURL
gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-contexts-$PROJECT_ID \
--member serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/storage.admin

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/iam.serviceAccountTokenCreator

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/serviceusage.serviceUsageConsumer

# removida a permissão abaixo para manter o princípio do menor previlégio
#gcloud projects add-iam-policy-binding $PROJECT_ID \
#--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
#--role roles/storage.admin
   
# Usuário da aplicação = permissão no IAP    
gcloud projects add-iam-policy-binding $PROJECT_ID --member=group:$USER_GROUP --role=roles/iap.httpsResourceAccessor

# permissão no Gemini Cloud/Code Assist
gcloud projects add-iam-policy-binding $PROJECT_ID --member=group:$USER_GROUP --role=roles/cloudaicompanion.user
gcloud projects add-iam-policy-binding $PROJECT_ID --member=group:$USER_GROUP --role=roles/serviceusage.serviceUsageViewer

# o trecho a seguir é somente se o usuário que continuara atuali\ando as versões é diferente e terá menos permissões
gcloud projects add-iam-policy-binding $PROJECT_ID --member=group:$DEPLOY_GROUP --role=roles/viewer
gcloud projects add-iam-policy-binding $PROJECT_ID --member=group:$DEPLOY_GROUP --role=roles/cloudbuild.builds.editor
gcloud projects add-iam-policy-binding $PROJECT_ID --member=group:$DEPLOY_GROUP --role=roles/appengine.appAdmin
gcloud storage buckets add-iam-policy-binding gs://staging.$PROJECT_ID.appspot.com \
   --member=group:$DEPLOY_GROUP --role=roles/storage.objectUser --project=$PROJECT_ID
gcloud iam service-accounts add-iam-policy-binding gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --member=group:$DEPLOY_GROUP --role=roles/iam.serviceAccountUser

### Permissão nos buckets - não tem a ver com o redeploy e sim com subir os projetos
gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-contexts-$PROJECT_ID \
   --member=group:$DEPLOY_GROUP --role=roles/storage.objectUser --project=$PROJECT_ID

gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-code-$PROJECT_ID \
   --member=group:$DEPLOY_GROUP --role=roles/storage.objectUser --project=$PROJECT_ID

#deploy em Cloud Run (não é necessário yaml)
gcloud services enable run.googleapis.com
#deploy em Cloud Run (não é necessário yaml)
gcloud beta run deploy $SERVICE_NAME --source . --region=$REGION \
   --service-account=$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
   --project=$PROJECT_ID --no-allow-unauthenticated --iap --min-instances=0  
   --verbosity=debug 
   --quiet
# deploys seguintes (omitir o service account)
# --cpu-throttling (CPU not allways allocated) and -no-allow-unauthenticated are default

# CONFIGURAR A autenticação com IAP (Criar o LB e configurar)
# Configurar o IAP
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID | grep projectNumber | grep -Eo '[0-9]+')
echo $PROJECT_NUMBER
gcloud beta services identity create --service=iap.googleapis.com --project=$PROJECT_ID
gcloud run services add-iam-policy-binding $SERVICE_NAME --member serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
--role='roles/run.invoker' --region $REGION

gcloud iap oauth-brands create --application_title=GeminiApp --support_email=$SUPPORT_EMAIL
gcloud iap oauth-clients create BRAND --display_name=GeminiApp
gcloud iap web enable --resource-type=backend-services --service=$SERVICE_NAME-backend
    
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL" --role=roles/iap.httpsResourceAccessor


#### OUTRAS ESTRATÉGIAS DE DEPLOY NO CLOUD RUN

gcloud builds submit --tag gcr.io/$PROJECT_ID/gem-app
gcloud run deploy delete --image=gcr.io/$PROJECT_ID/gem-app --region=$REGION --allow-unauthenticated
  
gcloud run deploy $SERVICE_NAME-no-thread --region=$REGION --source . --memory=4Gi --cpu=2 --min-instances=1 --max-instances=1 --concurrency=100 --timeout=15m \
   --ingress=internal-and-cloud-load-balancing --no-allow-unauthenticated  --cpu-throttling  \
   --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com 

gcloud run deploy $SERVICE_NAME-gunicorn-thread --region=$REGION --image=gcr.io/$PROJECT_ID/gem-app --memory=4Gi --cpu=2 --min-instances=1 --max-instances=1 --concurrency=100 --timeout=15m \
   --allow-unauthenticated  --cpu-throttling  \
   --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com 