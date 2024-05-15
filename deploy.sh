gcloud config set project <projecto a ser usado> #- rodar se "gcloud config get project" retornar um projeto diferente do desejado
export PROJECT_ID=$(gcloud config get project)
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

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/serviceusage.serviceUsageConsumer

gcloud services enable storage-component.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable appengine.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable iap.googleapis.com 
gcloud services enable vision.googleapis.com

gcloud app create --project=$PROJECT_ID --region=$REGION --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com

gcloud app deploy --project=$PROJECT_ID --quiet

gcloud iap oauth-brands create --application_title=GeminiApp --support_email=$SUPPORT_EMAIL
gcloud iap oauth-clients create BRAND --display_name=GeminiApp
gcloud iap web enable --resource-type=app-engine 
    
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL" --role=roles/iap.httpsResourceAccessor


# o trecho a seguir é somente se o usuário que continuara atualziando as versões é diferente e terá menos permissões
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL_DEPLOY" --role=roles/appengine.appAdmin
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL_DEPLOY" --role=roles/cloudbuild.builds.editor
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL_DEPLOY" --role=roles/storage.admin
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL_DEPLOY" --role=roles/viewer
gcloud iam service-accounts add-iam-policy-binding gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --member="user:$USER_EMAIL_DEPLOY" \
    --role="roles/iam.serviceAccountUser"

# permissões necessárias caso o deploy seja feito no AppEngine Flexible/Cloud Run (?)
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/logging.logWriter
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role --role=roles/monitoring.metricWriter


#deploy em Cloud Run (não é necessário yaml)
export SERVICE_NAME=gemini-app-ui
# primeiro deploy
gcloud run deploy $SERVICE_NAME --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com --region=$REGION --source . --quiet
# deploys seguintes (omitir o service account)
gcloud run deploy $SERVICE_NAME --region=$REGION --source . --quiet

# CONFIGURAR A autenticação com IAP (Criar o LB e configurar)

# Para o Cloud Run usar o IAP como autenticador, ele precisar ter um Load Balancer na frente
gcloud compute addresses create $SERVICE_NAME--lb-ip --network-tier=PREMIUM --ip-version=IPV4 --global
export LB_IP_NUMBER=$(gcloud compute addresses describe $SERVICE_NAME--lb-ip --format="get(address)" --global)
# Crie um NEG sem servidor para o app sem servidor para o Cloud Run
gcloud compute network-endpoint-groups create $SERVICE_NAME-serverless-neg --region=$REGION \
       --network-endpoint-type=serverless --cloud-run-service=$SERVICE_NAME
#Crie um serviço de back-end
gcloud compute backend-services create $SERVICE_NAME-backend --load-balancing-scheme=EXTERNAL_MANAGED --global
# Adicione o NEG sem servidor como um back-end ao serviço de back-end
gcloud compute backend-services add-backend $SERVICE_NAME-backend  --global \
       --network-endpoint-group=$SERVICE_NAME-serverless-neg   --network-endpoint-group-region=$REGION

# Crie o LB
gcloud compute url-maps create $SERVICE_NAME-lb --default-service $SERVICE_NAME-backend 

# Cria o frontend (LB) HTTP
gcloud compute target-http-proxies create $SERVICE_NAME-http-proxy  --url-map=$SERVICE_NAME-lb
gcloud compute forwarding-rules create $SERVICE_NAME-http-fw-rule  --address=$LB_IP_NUMBER --global --ports=80 \
   --target-http-proxy=$SERVICE_NAME-http-proxy --load-balancing-scheme=EXTERNAL_MANAGED  --network-tier=PREMIUM 
 
# Cria o frontend (LB) HTTPS
gcloud compute ssl-certificates create $SERVICE_NAME-ssl-cert --domains **DOMAIN**
gcloud compute target-https-proxies create $SERVICE_NAME-https-proxy  --url-map=$SERVICE_NAME-lb  --ssl-certificates=$SERVICE_NAME-ssl-cert
gcloud compute forwarding-rules create $SERVICE_NAME-https-fw-rule  --address=$LB_IP_NUMBER --global --ports=443 \
   --target-https-proxy=$SERVICE_NAME-https-proxy --load-balancing-scheme=EXTERNAL_MANAGED  --network-tier=PREMIUM 

      
# Configurar o IAP para o LB
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID | grep projectNumber | grep -Eo '[0-9]+')
gcloud beta services identity create --service=iap.googleapis.com --project=$PROJECT_ID
gcloud run services add-iam-policy-binding $SERVICE_NAME --member=serviceAccount:service-$PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com  \
--role='roles/run.invoker'
# Escopo Global
gcloud compute backend-services update $SERVICE_NAME-backend --global --iap=enabled
# OU Escopo Regional
gcloud compute backend-services update $SERVICE_NAME-backend --region $REGION --iap=enabled