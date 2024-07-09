export PROJECT_ID=$(gcloud config get project)
echo $PROJECT_ID
export REGION=southamerica-east1
export SUPPORT_EMAIL=dev@fbatagin.altostrat.com
export USER_GROUP=gcp-devops@fbatagin.altostrat.com
export DEPLOY_GROUP=gcp-devops@fbatagin.altostrat.com


gcloud services enable storage-component.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable appengine.googleapis.com
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

# removida a permissão abaixo para manter o princípio do menor previlégio
#gcloud projects add-iam-policy-binding $PROJECT_ID \
#--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
#--role roles/storage.admin

##### --- deploy em GAE Standard --- #####
gcloud app create --project=$PROJECT_ID --region=$REGION --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com

gcloud app deploy --project=$PROJECT_ID --quiet
gcloud app firewall-rules update default --action DENY
gcloud app firewall-rules create 100 --action ALLOW --source-range <CIDR> --description "Limitando ao acesso da rede corporativa"
# Ou somente tráfego interno 
gcloud app services update default --ingress=internal-only

gcloud iap oauth-brands create --application_title=GeminiApp --support_email=$SUPPORT_EMAIL
gcloud iap oauth-clients create BRAND --display_name=GeminiApp
gcloud iap web enable --resource-type=app-engine 
    
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

##### --- deploy em GAE Flexible --- #####
gcloud services enable run.googleapis.com
# permissões necessárias caso o deploy seja feito no AppEngine Flexible/Cloud Run (?)
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/logging.logWriter
gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role=roles/monitoring.metricWriter


#deploy em Cloud Run (não é necessário yaml)
export SERVICE_NAME=gemini-app-ui
gcloud services enable run.googleapis.com
# primeiro deploy
gcloud run deploy $SERVICE_NAME --region=$REGION --source . --memory=4Gi --cpu=2 --min-instances=1 --max-instances=1 --concurrency=100 --timeout=15m \
   --ingress=internal-and-cloud-load-balancing --no-allow-unauthenticated  --cpu-throttling --quiet \
   --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com 
# deploys seguintes (omitir o service account)
# --cpu-throttling (CPU not allways allocated) and -no-allow-unauthenticated are default


# CONFIGURAR A autenticação com IAP (Criar o LB e configurar)

# LOAD BALANCER - INTERNO (PEDIDO DASA - se acessível somente na rede interna) - # LOAD BALANCER - INTERNO (PEDIDO DASA - se acessível somente na rede interna)
gcloud services enable compute.googleapis.com
gcloud compute networks create default --project=$PROJECT_ID --subnet-mode=custom --mtu=1460 --bgp-routing-mode=global
gcloud compute networks subnets create default --project=$PROJECT_ID --network=default --region=$REGION --range=10.0.0.0/24
# Proxy-only subnet é uma necessiadae do LBs baseados em Envoy proxy. Assim teoricamente, os INTERNAL e EXTERNAL (não MANAGED) não necessitariam. Mas eu não testei
# Eles são o Classic (HTTP e TCP) e TCP passthroough - ref: https://cloud.google.com/load-balancing/docs/choosing-load-balancer
gcloud compute networks subnets create proxy-only-subnet --project=$PROJECT_ID --network=default --region=$REGION --range=10.255.0.0/24 --purpose=REGIONAL_MANAGED_PROXY --role=ACTIVE

# Crie um NEG sem servidor para o app sem servidor para o Cloud Run
gcloud compute network-endpoint-groups create $SERVICE_NAME-serverless-neg --region=$REGION \
    --network-endpoint-type=serverless --cloud-run-service=$SERVICE_NAME
#Crie um serviço de back-end
gcloud compute backend-services create $SERVICE_NAME-backend --load-balancing-scheme=INTERNAL_MANAGED --region=$REGION --protocol=HTTPS
# Adicione o NEG sem servidor como um back-end ao serviço de back-end
gcloud compute backend-services add-backend $SERVICE_NAME-backend --region=$REGION \
    --network-endpoint-group=$SERVICE_NAME-serverless-neg --network-endpoint-group-region=$REGION
# Cria o frontend (LB) HTTP
gcloud compute url-maps create $SERVICE_NAME-lb --default-service $SERVICE_NAME-backend --region=$REGION
# Cria o frontend (LB) HTTP-proxy (NÃO FUNCIONA COM O IAP QUE REQUER HTTPS)
gcloud compute target-http-proxies create $SERVICE_NAME-http-proxy  --url-map=$SERVICE_NAME-lb --region=$REGION 
gcloud compute forwarding-rules create $SERVICE_NAME-http-fw-rule --region=$REGION --ports=80 --network=default --subnet=default \
   --target-http-proxy-region=$REGION --target-http-proxy=$SERVICE_NAME-http-proxy --load-balancing-scheme=INTERNAL_MANAGED
# Cria o frontend (LB) HTTPS-proxy
openssl genrsa -out private.key 2048
openssl req -new -x509 -key private.key -out certificate.crt -days 3650
gcloud compute ssl-certificates create $SERVICE_NAME-ssl-cert --project=$PROJECT_ID --certificate=certificate.crt --private-key=private.key --region=$REGION
gcloud compute target-https-proxies create $SERVICE_NAME-https-proxy  --region=$REGION --url-map=$SERVICE_NAME-lb  --ssl-certificates=$SERVICE_NAME-ssl-cert
gcloud compute forwarding-rules create $SERVICE_NAME-https-fw-rule  --region=$REGION --ports=443 --network=default --subnet=default \
   --target-https-proxy-region=$REGION --target-https-proxy=$SERVICE_NAME-https-proxy --load-balancing-scheme=INTERNAL_MANAGED \
   --allow-global-access --address=10.0.0.10 # o endereço especifico pode ser passado opcionalmente  e o Global access é pra permitir que outras regiões cheguem no IP via peering

##gcloud compute addresses create $SERVICE_NAME--lb-int-ip --project=$PROJECT_ID --region=$REGION --address-type=INTERNAL \
##   --subnet=projects/$PROJECT_ID/regions/$REGION/subnetworks/default --purpose=GCE_ENDPOINT
##export LB_IP_NUMBER=$(gcloud compute addresses describe $SERVICE_NAME--lb-int-ip --format="get(address)")
##gcloud compute firewall-rules create fw-allow-lb-access --network=default --action=allow --direction=ingress \
##    --source-ranges=10.0.0.0/24 --rules=tcp,udp,icmp
##gcloud compute firewall-rules create fw-allow-health-check --network=lb-network --action=allow --direction=ingress \
##    --target-tags=allow-health-check --source-ranges=130.211.0.0/22,35.191.0.0/16 --rules=tcp,udp,icmp    

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
gcloud compute target-http-proxies create $SERVICE_NAME-http-proxy  --url-map=$SERVICE_NAME-lb
gcloud compute forwarding-rules create $SERVICE_NAME-http-fw-rule  --address=$LB_IP_NUMBER --global --ports=80 \
   --target-http-proxy=$SERVICE_NAME-http-proxy --load-balancing-scheme=EXTERNAL_MANAGED  --network-tier=PREMIUM 
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
    
gcloud projects add-iam-policy-binding $PROJECT_ID --member="user:$USER_EMAIL" --role=roles/iap.httpsResourceAccessor

# Escopo Global
gcloud compute backend-services update $SERVICE_NAME-backend --global --iap=enabled
# OU Escopo Regional
gcloud compute backend-services update $SERVICE_NAME-backend --region $REGION --iap=enabled



#### OUTRAS ESTRATÉGIAS DE DEPLOY NO CLOUD RUN

gcloud builds submit --tag gcr.io/$PROJECT_ID/gem-app
gcloud run deploy delete --image=gcr.io/$PROJECT_ID/gem-app --region=$REGION --allow-unauthenticated
  
gcloud run deploy $SERVICE_NAME-no-thread --region=$REGION --source . --memory=4Gi --cpu=2 --min-instances=1 --max-instances=1 --concurrency=100 --timeout=15m \
   --ingress=internal-and-cloud-load-balancing --no-allow-unauthenticated  --cpu-throttling  \
   --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com 

gcloud run deploy $SERVICE_NAME-gunicorn-thread --region=$REGION --image=gcr.io/$PROJECT_ID/gem-app --memory=4Gi --cpu=2 --min-instances=1 --max-instances=1 --concurrency=100 --timeout=15m \
   --allow-unauthenticated  --cpu-throttling  \
   --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com 