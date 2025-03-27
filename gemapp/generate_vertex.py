from vertexai.generative_models import GenerativeModel, SafetySetting, Part
import vertexai

vertexai.init()

generation_config = {
    "max_output_tokens": 8192,
    "temperature": 1,
    "top_p": 0.95,
}

safety_settings = [
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=SafetySetting.HarmBlockThreshold.OFF
    ),
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=SafetySetting.HarmBlockThreshold.OFF
    ),
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=SafetySetting.HarmBlockThreshold.OFF
    ),
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=SafetySetting.HarmBlockThreshold.OFF
    ),
]

def getPartClass():
   return Part

def generate(model_name, parts):
    print("METHOD: generate_vertex")
    model = GenerativeModel(model_name, generation_config=generation_config, safety_settings=safety_settings)
    return model.generate_content(parts).text

def getGenerativeModel(model_name):
    return GenerativeModel(model_name, generation_config=generation_config, safety_settings=safety_settings)