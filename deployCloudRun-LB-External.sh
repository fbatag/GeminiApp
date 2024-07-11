export PROJECT_ID=$(gcloud config get project)
echo $PROJECT_ID
export REGION=southamerica-east1
export SUPPORT_EMAIL=dev@fbatagin.altostrat.com
export USER_GROUP=gcp-devops@fbatagin.altostrat.com
export DEPLOY_GROUP=gcp-devops@fbatagin.altostrat.com


gcloud services enable storage-component.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable cloudbuild.googleapis.com # para o Cloud Run
gcloud services enable iap.googleapis.com 
#gcloud services enable vision.googleapis.com # para covnersão de pdf em texto - não usado atualmente

gsutil mb -b on -l southamerica-east1 gs://gen-ai-app-contexts-$PROJECT_ID
gsutil lifecycle set bucket_lifecycle.json gs://gen-ai-app-contexts-$PROJECT_ID

gsutil mb -b on -l southamerica-east1 gs://gen-ai-app-code-$PROJECT_ID
gsutil lifecycle set bucket_lifecycle.json gs://gen-ai-app-code-$PROJECT_ID

gcloud iam service-accounts create gemini-app-sa \
--display-name "Gemini App Generator Service Account" \
--project $PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/aiplatform.user

gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-contexts-$PROJECT_ID \
--member=serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/storage.objectUser --project=$PROJECT_ID

gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-code-$PROJECT_ID \
--member=serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/storage.objectUser --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/serviceusage.serviceUsageConsumer

### Permissão nos buckets - não tem a ver com o redeploy e sim com subir os projetos
gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-contexts-$PROJECT_ID \
   --member=group:$DEPLOY_GROUP --role=roles/storage.objectUser --project=$PROJECT_ID

gcloud storage buckets add-iam-policy-binding gs://gen-ai-app-code-$PROJECT_ID \
   --member=group:$DEPLOY_GROUP --role=roles/storage.objectUser --project=$PROJECT_ID

#deploy em Cloud Run (não é necessário yaml)
export SERVICE_NAME=gemini-app-ui
export PROJECT_ID=$(gcloud config get project)
export REGION=southamerica-east1
export USER_GROUP=gcp-devops@fbatagin.altostrat.com
export SUPPORT_EMAIL=dev@fbatagin.altostrat.com

gcloud services enable run.googleapis.com
# primeiro deploy
gcloud config set region/run $REGION
gcloud run deploy $SERVICE_NAME --region=$REGION --source . --memory=4Gi --cpu=2 --min-instances=1 --max-instances=1 --concurrency=100 --timeout=60m \
   --project=$PROJECT_ID --ingress=internal-and-cloud-load-balancing --no-allow-unauthenticated  --cpu-throttling --quiet \
   --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com 
# deploys seguintes (omitir o service account)
# --cpu-throttling (CPU not allways allocated) and -no-allow-unauthenticated are default

# CONFIGURAR A autenticação com IAP (Criar o LB e configurar)

# LOAD BALANCER - EXTERNO - # LOAD BALANCER - INTERNO (PEDIDO DASA - se acessível somente na rede interna)
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
# Cria o frontend (LB) HTTP-proxy (NÃO FUNCIONA COM O IAP QUE REQUER HTTPS)
#gcloud compute target-http-proxies create $SERVICE_NAME-http-proxy  --url-map=$SERVICE_NAME-lb
#gcloud compute forwarding-rules create $SERVICE_NAME-http-fw-rule  --address=$LB_IP_NUMBER --global --ports=80 \
#   --target-http-proxy=$SERVICE_NAME-http-proxy --load-balancing-scheme=EXTERNAL_MANAGED  --network-tier=PREMIUM 
# Cria o frontend (LB) HTTPS-proxy
gcloud compute ssl-certificates create $SERVICE_NAME-ssl-cert --domains **DOMAIN**
gcloud compute target-https-proxies create $SERVICE_NAME-https-proxy  --url-map=$SERVICE_NAME-lb  --ssl-certificates=$SERVICE_NAME-ssl-cert
gcloud compute forwarding-rules create $SERVICE_NAME-https-fw-rule  --address=$LB_IP_NUMBER --global --ports=443 \
   --target-https-proxy=$SERVICE_NAME-https-proxy --load-balancing-scheme=EXTERNAL_MANAGED  --network-tier=PREMIUM 


# Configurar o IAP para o LB
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID | grep projectNumber | grep -Eo '[0-9]+')
echo $PROJECT_NUMBER
gcloud beta services identity create --service=iap.googleapis.com --project=$PROJECT_ID
gcloud run services add-iam-policy-binding $SERVICE_NAME --member=serviceAccount:service-$PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com  \
--role='roles/run.invoker' 

gcloud iap oauth-brands create --application_title=GeminiApp --support_email=$SUPPORT_EMAIL
gcloud iap oauth-clients create BRAND --display_name=GeminiApp
gcloud iap web enable --resource-type=backend-services --service=$SERVICE_NAME-backend
    
# Usuário da aplicação = permissão no IAP    
gcloud projects add-iam-policy-binding $PROJECT_ID --member=group:$USER_GROUP --role=roles/iap.httpsResourceAccessor

# Escopo Global
gcloud compute backend-services update $SERVICE_NAME-backend --global --iap=enabled
# OU Escopo Regional
gcloud compute backend-services update $SERVICE_NAME-backend --region $REGION --iap=enabled
