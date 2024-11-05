export PROJECT_ID=$(gcloud config get project)
echo $PROJECT_ID
export REGION=southamerica-east1
export SERVICE_NAME=gemini-app-ui

export SHARED_VPC_PROJECT_ID=shared-vpc-gem-app
export SHARED_VPC_NAME=shared
export SHARED_SUBNET_NAME=shared

export SUPPORT_EMAIL=dev@fbatagin.altostrat.com
export USER_GROUP=gcp-devops@fbatagin.altostrat.com
export DEPLOY_GROUP=gcp-devops@fbatagin.altostrat.com


gcloud services enable iam.googleapis.com
gcloud services enable storage-component.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable cloudbuild.googleapis.com # para o Cloud Run
gcloud services enable iap.googleapis.com 
gcloud services enable run.googleapis.com
#gcloud services enable vision.googleapis.com # para covnersão de pdf em texto - não usado atualmente

gsutil mb -b on -l $REGION gs://gen-ai-app-contexts-$PROJECT_ID
gsutil lifecycle set bucket_lifecycle.json gs://gen-ai-app-contexts-$PROJECT_ID
gcloud storage buckets update gs://gen-ai-app-contexts-$PROJECT_ID --cors-file=bucket-cors.json
gcloud storage buckets describe gs://gen-ai-app-contexts-$PROJECT_ID --format="default(cors_config)" # Verirficar se acatou

gsutil mb -b on -l $REGION gs://gen-ai-app-code-$PROJECT_ID
gsutil lifecycle set bucket_lifecycle.json gs://gen-ai-app-code-$PROJECT_ID
gcloud storage buckets update gs://gen-ai-app-code-$PROJECT_ID --cors-file=bucket-cors.json
gcloud storage buckets describe gs://gen-ai-app-code-$PROJECT_ID --format="default(cors_config)" # Verirficar se acatou

gcloud iam service-accounts create gemini-app-sa \
--display-name "Gemini App Generator Service Account" \
--project $PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/aiplatform.user

gcloud projects add-iam-policy-binding $PROJECT_ID \
--member serviceAccount:gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com \
--role roles/iam.serviceAccountTokenCreator

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



gcloud config set run/region $REGION
gcloud run deploy $SERVICE_NAME --region=$REGION --source . --memory=4Gi --cpu=2 --min-instances=1 --max-instances=1 --concurrency=100 --timeout=60m \
   --project=$PROJECT_ID --ingress=internal-and-cloud-load-balancing --no-allow-unauthenticated  --cpu-throttling --quiet \
   --service-account=gemini-app-sa@$PROJECT_ID.iam.gserviceaccount.com 
# deploys seguintes (omitir o service account)
# --cpu-throttling (CPU not allways allocated) and -no-allow-unauthenticated are default

# CONFIGURAR A autenticação com IAP (Criar o LB e configurar)

# CRIAR A PROXY-ONLY-SUBNET NA SHARED VPC E COMPARTILHA COM O PROJETO 
gcloud compute networks subnets create proxy-only-subnet --project=$SHARED_VPC_PROJECT_ID --network=$SHARED_VPC_NAME --region=$REGION \
   --range=10.161.0.0/26 --purpose=REGIONAL_MANAGED_PROXY --role=ACTIVE

# Crie um NEG sem servidor para o app sem servidor para o Cloud Run (essa lina é em comum com TODOS LOAD BALANCERS)
gcloud compute network-endpoint-groups create $SERVICE_NAME-serverless-neg --region=$REGION \
       --network-endpoint-type=serverless --cloud-run-service=$SERVICE_NAME

#Crie um serviço de back-end para Load balancer interno
gcloud compute backend-services create $SERVICE_NAME-backend-int --load-balancing-scheme=INTERNAL_MANAGED --region=$REGION --protocol=HTTPS
# Adicione o NEG sem servidor como um back-end ao serviço de back-end
gcloud compute backend-services add-backend $SERVICE_NAME-backend-int --region=$REGION \
    --network-endpoint-group=$SERVICE_NAME-serverless-neg --network-endpoint-group-region=$REGION


# Cria o frontend (LB) 
gcloud compute url-maps create $SERVICE_NAME-int-lb --default-service $SERVICE_NAME-backend-int --region=$REGION

# Cria o frontend (LB) HTTPS-proxy
export ILB_IP_NUMBER=10.158.0.5
export FRONTEND_TYPE=ip
openssl genrsa -out $FRONTEND_TYPE-private.pem 2048
openssl req -new -x509 -key $FRONTEND_TYPE-private.pem -out $FRONTEND_TYPE-certificate.crt -days 3650 -subj "/C=BR/ST=SP/L=SaoPaulo/O=GoogleCloud/CN=$ILB_IP_NUMBER"

# Reserva o endereço IP PRIVADO
gcloud compute addresses create $SERVICE_NAME-int-lb-$FRONTEND_TYPE --project=$PROJECT_ID --region=$REGION --purpose=SHARED_LOADBALANCER_VIP \
   --subnet=projects/$SHARED_VPC_PROJECT_ID/regions/$REGION/subnetworks/$SHARED_VPC_NAME \
   --addresses=$ILB_IP_NUMBER
# Cria o certificado no Google Certificate Manager 
gcloud compute ssl-certificates create $SERVICE_NAME-ssl-priv-cert-$FRONTEND_TYPE --project=$PROJECT_ID \
   --certificate=$FRONTEND_TYPE-certificate.crt --private-key=$FRONTEND_TYPE-private.pem --region=$REGION

# Cria o frontend (LB) HTTPS-proxy
gcloud compute target-https-proxies create $SERVICE_NAME-https-proxy-$FRONTEND_TYPE --region=$REGION \
   --url-map=$SERVICE_NAME-int-lb --ssl-certificates=$SERVICE_NAME-ssl-priv-cert-$FRONTEND_TYPE
# Reserva o IP (somente para garantir que o ip vai ficar fixo - não é obrigatório)
gcloud compute forwarding-rules create $SERVICE_NAME-https-fw-rule-$FRONTEND_TYPE --project=$PROJECT_ID --region=$REGION --ports=443 \
   --network=projects/$SHARED_VPC_PROJECT_ID/global/networks/$SHARED_VPC_NAME \
   --subnet=projects/$SHARED_VPC_PROJECT_ID/regions/$REGION/subnetworks/$SHARED_SUBNET_NAME \
   --target-https-proxy-region=$REGION --target-https-proxy=$SERVICE_NAME-https-proxy-$FRONTEND_TYPE --load-balancing-scheme=INTERNAL_MANAGED \
   --allow-global-access --address=$ILB_IP_NUMBER

export CA_POOL_NAME=dev-cert
export INTERNAL_DOMAIN=batapp.internal.batagin
export ILB_IP_NUMBER=10.158.0.4 # rodar a reserva de IP também se for o caso
export FRONTEND_TYPE=dm
gcloud privateca certificates create $SERVICE_NAME-ssl-priv-cert-$FRONTEND_TYPE --issuer-pool $CA_POOL_NAME --issuer-location $REGION \
   --use-preset-profile=leaf_server_tls --dns-san=$INTERNAL_DOMAIN \
   --cert-output-file=$FRONTEND_TYPE-certificate.crt --generate-key --key-output-file=$FRONTEND_TYPE-private.pem \
   --ca batagin --validity=P10Y 
   --name-permitted-dns=batapp.internal.batagin
   --subject=/C=BR/ST=SP/L=SaoPaulo/O=GoogleCloud/CN=batapp.internal.batagin

                 

# Repetir os dois comandos acima para esses novos valores

# Configurar o IAP para o LB
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID | grep projectNumber | grep -Eo '[0-9]+')
echo $PROJECT_NUMBER
gcloud beta services identity create --service=iap.googleapis.com --project=$PROJECT_ID
gcloud run services add-iam-policy-binding $SERVICE_NAME --member=serviceAccount:service-$PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com  \
--role='roles/run.invoker' --region $REGION

gcloud iap oauth-brands create --application_title=GeminiApp --support_email=$SUPPORT_EMAIL
gcloud iap oauth-clients create BRAND --display_name=GeminiApp
gcloud iap web enable --resource-type=backend-services --service=$SERVICE_NAME-backend
    
#configurar o IP Do LB como allowed domain no IAP
# https://cloud.google.com/iap/docs/allowed-domains?hl=pt-br#console

# Usuário da aplicação = permissão no IAP    
gcloud projects add-iam-policy-binding $PROJECT_ID --member=group:$USER_GROUP --role=roles/iap.httpsResourceAccessor

# Escopo Global
gcloud compute backend-services update $SERVICE_NAME-backend --global --iap=enabled
# OU Escopo Regional
gcloud compute backend-services update $SERVICE_NAME-backend --region $REGION --iap=enabled


# Por fim, para não ter erro no certificado, criar uma CA Authority privada, gerar um certificado a partir dela e associar a FW-rule a este cerficado no lugar 
# do auto assinado.
# No DNS criar uma managed Zone privada e criar um domain privado para ser associado 