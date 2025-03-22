# ATENÇÃO: Antes de rodar, definir e substituir os nomes <nome do projeto>, <nome do grupo uauário>, <nome aplicação>, <nome do bucket>

# Rodar esse comando se a região já estiver configurada (conferir com gcloud conf list)
export PROJECT_ID=$(gcloud config get project)

# Ou setar manualmente
export PROJECT_ID=<nome do projeto>

# confirmar que foi setado
echo $PROJECT_ID

# Definir o projeto como padrão
gcloud config set $PROJECT_ID

# definir a região onde a aplicação vai rodar
export REGION=europe-west2

# definir o user do IAP (só uma formalidade)
export SUPPORT_EMAIL=pmodesto@careplus.com.br

# Defini um grupo or usuário que terá acesso a essa aplicação
export USER_GROUP=<nome do grupo usuário>@careplus.com.br

# Definir uma nome para a aplicação
export SERVICE_NAME=<nome aplicação>

# Definir o nome do bucket sendo utilizado pela aplicação
export APP_BUCKET_NAME=<nome do bucket>

# definir noe do usuário com permissão de fazer o deploy na aplicação (já tomei a liberdade de colocar o nome do Pedro)
export DEPLOY_USER=pmodesto@careplus.com.br

gcloud run deploy $SERVICE_NAME --region=$REGION --source . --memory=4Gi --cpu=2 --min-instances=1 --max-instances=1 --concurrency=100 --timeout=60m \
   --project=$PROJECT_ID --allow-unauthenticated  --cpu-throttling \
   --service-account=$SERVICE_NAME-sa@$PROJECT_ID.iam.gserviceaccount.com 
