#from openai import OpenAI
#
#client = OpenAI(
#  base_url="https://openrouter.ai/api/v1",
#  api_key="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",
#)
#
#completion = client.chat.completions.create(
#  extra_body={},
#  model="x-ai/grok-4-fast:free",
#  messages=[
#    {
#      "role": "user",
#      "content": "write a sentence about five words about cats"
#    }
#  ]
#)
#print(str(completion.choices[0].message.content).rstrip())
#

import torch
from transformers import pipeline

# This will use the GPU on Apple Silicon if available
model = pipeline(
    "text-generation",
    model="meta-llama/Llama-3.2-1B-Instruct",
    device_map="auto",  # Add this line for Apple Silicon optimization
    torch_dtype=torch.float16  # Can reduce memory usage
)

prompt = "The future of renewable energy is"
results = model(prompt)

print(results[0]['generated_text'])