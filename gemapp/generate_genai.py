import os
from google import genai
from google.genai import types
from google.cloud import storage
storage_client = storage.Client()

region = os.environ.get("CLOUD_RUN_LOCATION", "us-central1")
#GOOGLE_CLOUD_PROJECT
client = genai.Client(vertexai=True, project=storage_client.project, location=region)

generate_content_config = types.GenerateContentConfig(
    temperature = 1,
    top_p = 0.95,
    max_output_tokens = 8192,
    response_modalities = ["TEXT"],
    safety_settings = [types.SafetySetting(
      category="HARM_CATEGORY_HATE_SPEECH",
      threshold="OFF"
    ),types.SafetySetting(
      category="HARM_CATEGORY_DANGEROUS_CONTENT",
      threshold="OFF"
    ),types.SafetySetting(
      category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
      threshold="OFF"
    ),types.SafetySetting(
      category="HARM_CATEGORY_HARASSMENT",
      threshold="OFF"
    )],
  )

def getPartClass():
   return types.Part

def generate(model_name, parts):
  print("METHOD: generate_genai - " + model_name)
  contents = [types.Content(role="user", parts=parts)]
  return client.models.generate_content(
    model = model_name,
    contents = contents,
    config = generate_content_config).text

def generate2(model_name, parts):
  print("METHOD: generate_genai")
  client = genai.Client(vertexai=True, project=storage_client.project, location=region)
  contents = [types.Content(role="user",parts=parts)]
  response = ""
  for chunk in client.models.generate_content_stream(
    model = model_name,
    contents = contents,
    config = generate_content_config):
      response += chunk.text
  return response
