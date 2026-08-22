// llmProviders.js

const PROVIDER_CONFIGS = {
  nvidia: {
    endpoint: "https://integrate.api.nvidia.com/v1/chat/completions",
    formatHeaders: (key) => ({
      "Authorization": `Bearer ${key}`,
      "Content-Type": "application/json",
      "Accept": "application/json"
    }),
    formatBody: (model, systemPrompt, userPrompt) => ({
      model: model,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt }
      ],
      max_tokens: 2000,
      temperature: 0.1,
      chat_template_kwargs: { enable_thinking: false },
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "quiz_responses",
          schema: {
            type: "object",
            properties: {
              responses: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    question_id: { type: "string" },
                    reasoning: { type: "string" },
                    chosen: { type: "array", items: { type: "string" } },
                    answer: { type: "string" }
                  },
                  required: ["question_id", "reasoning"]
                }
              }
            },
            required: ["responses"]
          }
        }
      }
    }),
    parseResponse: (json) => JSON.parse(json.choices[0].message.content)
  },
  openai: {
    endpoint: "https://api.openai.com/v1/chat/completions",
    formatHeaders: (key) => ({
      "Authorization": `Bearer ${key}`,
      "Content-Type": "application/json"
    }),
    formatBody: (model, systemPrompt, userPrompt) => ({
      model: model,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt }
      ],
      temperature: 0.1,
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "quiz_responses",
          strict: true,
          schema: {
            type: "object",
            properties: {
              responses: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    question_id: { type: "string" },
                    reasoning: { type: "string" },
                    chosen: { type: "array", items: { type: "string" } },
                    answer: { type: "string" }
                  },
                  required: ["question_id", "reasoning", "chosen", "answer"],
                  additionalProperties: false
                }
              }
            },
            required: ["responses"],
            additionalProperties: false
          }
        }
      }
    }),
    parseResponse: (json) => JSON.parse(json.choices[0].message.content)
  },
  anthropic: {
    endpoint: "https://api.anthropic.com/v1/messages",
    formatHeaders: (key) => ({
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json"
    }),
    formatBody: (model, systemPrompt, userPrompt) => ({
      model: model,
      system: systemPrompt,
      messages: [
        { role: "user", content: userPrompt + "\n\nPlease respond ONLY with a valid JSON object matching the requested schema." }
      ],
      max_tokens: 2000,
      temperature: 0.1,
    }),
    parseResponse: (json) => {
      let text = json.content[0].text;
      const start = text.indexOf("{");
      const end = text.lastIndexOf("}");
      if (start !== -1 && end !== -1) {
         text = text.slice(start, end + 1);
      }
      return JSON.parse(text);
    }
  },
  gemini: {
    endpoint: (key) => "", 
    formatHeaders: () => ({
      "Content-Type": "application/json"
    }),
    formatBody: (model, systemPrompt, userPrompt) => ({
      systemInstruction: { parts: [{ text: systemPrompt }] },
      contents: [{ parts: [{ text: userPrompt }] }],
      generationConfig: {
        temperature: 0.1,
        responseMimeType: "application/json",
      }
    }),
    parseResponse: (json) => JSON.parse(json.candidates[0].content.parts[0].text)
  }
};

let currentKeyIndex = 0;

export async function callLLMProvider(providerName, apiKeys, modelName, systemPrompt, userPrompt) {
  const provider = PROVIDER_CONFIGS[providerName];
  if (!provider) throw new Error("Unsupported provider: " + providerName);

  for (let attempt = 0; attempt < apiKeys.length; attempt++) {
    const key = apiKeys[currentKeyIndex];
    
    let endpoint = provider.endpoint;
    if (providerName === "gemini") {
       endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${modelName}:generateContent?key=${key}`;
    }

    const headers = provider.formatHeaders(key);
    const body = provider.formatBody(modelName, systemPrompt, userPrompt);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: headers,
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        if (response.status === 429 || response.status === 401 || response.status === 402) {
            console.warn(`Key ${currentKeyIndex} failed with ${response.status}. Trying next key...`);
            currentKeyIndex = (currentKeyIndex + 1) % apiKeys.length;
            if (attempt === apiKeys.length - 1) {
               throw new Error(`API Error ${response.status}: ${await response.text()}`);
            }
            continue; // try next key
        }
        throw new Error(`API Error ${response.status}: ${await response.text()}`);
      }

      const json = await response.json();
      return provider.parseResponse(json);

    } catch (e) {
      if (attempt === apiKeys.length - 1) throw e;
      currentKeyIndex = (currentKeyIndex + 1) % apiKeys.length;
    }
  }
}
