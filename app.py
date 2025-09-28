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
from transformers import pipeline, AutoTokenizer

# Enhanced Apple Silicon optimization
if torch.backends.mps.is_available():
    device = "mps"
    # MPS-specific optimizations
    torch.mps.set_per_process_memory_fraction(0.8)  # Limit memory usage to 80%
    torch_dtype = torch.float16
else:
    device = "cpu"
    torch_dtype = torch.float32

print(f"Using device: {device}")

model_name = "meta-llama/Llama-3.2-1B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_name)

model = pipeline(
    "text-generation",
    model=model_name,
    tokenizer=tokenizer,
    device=device,  # Explicit device assignment
    torch_dtype=torch_dtype,
    model_kwargs={
        "low_cpu_mem_usage": True,
        "offload_folder": "./offload"  # Folder for offloading if needed
    }
)

system_prompt = (
            "Ты — помощник по аналитическим запросам Postgres. "
            "Пиши только валидный SQL для Postgres. Используй ТОЛЬКО предоставленную схему и правила. "
            "Только SELECT, явные JOIN. Не придумывай таблицы/колонки. Добавляй LIMIT если нет."
            "Не пиши текстовых дополнений"
        )
user_prompt = (
            "Ответь строго JSON с полями: {\"sql\": \"...\", \"needs_clarification\": false, \"clarification_question\": \"\"}."
            +"Запрос пользователя: Все задачи моей компании за сентябрь 2025"
        )


# Rest of your code remains the same...
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt}
]

formatted_prompt = tokenizer.apply_chat_template(
    messages, 
    tokenize=False,
    add_generation_prompt=True
)

# Add batch size optimization for MPS
generation_kwargs = {
    "max_new_tokens": 100,
    "temperature": 0.1,
    "do_sample": False,
    "return_full_text": False,
    "pad_token_id": tokenizer.eos_token_id,
}

if device == "mps":
    generation_kwargs["batch_size"] = 1  # Optimize for MPS

results = model(formatted_prompt, **generation_kwargs)
response = results[0]['generated_text'].strip()
print(response)