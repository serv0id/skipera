export function parseJsonText(text) {
  if (!text) return { responses: [] };
  if (typeof text !== "string") return text;
  let cleaned = text.replace(/```json/gi, "").replace(/```/g, "").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start !== -1 && end !== -1) {
    cleaned = cleaned.slice(start, end + 1);
  }
  try {
    return JSON.parse(cleaned);
  } catch (e) {
    console.warn("[Skipera LLM] JSON parse failed, salvaging individual responses:", text);
    const salvaged = salvageResponses(text);
    if (salvaged.length > 0) {
      console.warn(`[Skipera LLM] Salvaged ${salvaged.length} response object(s) from malformed JSON.`);
      return { responses: salvaged };
    }
    throw e;
  }
}

// Long generations occasionally corrupt a single object (a duplicated key, a stray
// token). Parsing the array as a whole then costs every answer in the batch, so
// split on the object delimiter and parse each independently — one bad object
// costs one answer, and the caller's re-ask fills that gap.
// ponytail: splits on `},{` rather than tracking brace depth, because a corrupt
// object desyncs quote state and swallows everything after it. Literal `},{`
// inside a reasoning string would mis-split; hasn't been seen, and a mis-split
// chunk just fails to parse and gets dropped like any other bad object.
function salvageResponses(text) {
  const key = text.indexOf('"responses"');
  if (key === -1) return [];
  const arrStart = text.indexOf("[", key);
  const arrEnd = text.lastIndexOf("]");
  if (arrStart === -1 || arrEnd <= arrStart) return [];

  const out = [];
  for (let chunk of text.slice(arrStart + 1, arrEnd).split(/\}\s*,\s*\{/)) {
    chunk = chunk.trim();
    if (!chunk.startsWith("{")) chunk = "{" + chunk;
    if (!chunk.endsWith("}")) chunk += "}";
    try {
      const obj = JSON.parse(chunk);
      if (obj && obj.question_id != null) out.push(obj);
    } catch (inner) { /* drop just this object */ }
  }
  return out;
}

const PROVIDER_CONFIGS = {
  nvidia: {
    endpoint: "https://integrate.api.nvidia.com/v1/chat/completions",
    formatHeaders: (key) => ({
      "Authorization": `Bearer ${key.trim()}`,
      "Content-Type": "application/json",
      "Accept": "application/json"
    }),
    formatBody: (model, systemPrompt, userPrompt) => {
      const fullSystem = `${systemPrompt}\n\nCRITICAL: You must respond with a valid JSON object matching this schema:\n${JSON.stringify({
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
      })}`;

      return {
        model: model,
        messages: [
          { role: "user", content: `${fullSystem}\n\n${userPrompt}` }
        ],
        max_tokens: 8192,
        temperature: 0.1,
        top_p: 1.0,
        stream: false,
        chat_template_kwargs: { enable_thinking: false }
      };
    },
    parseResponse: (json) => {
      const choice = json?.choices?.[0];
      const text = choice?.message?.content || choice?.text || choice?.message?.reasoning_content || "";
      return parseJsonText(text);
    }
  },
  openai: {
    endpoint: "https://api.openai.com/v1/chat/completions",
    formatHeaders: (key) => ({
      "Authorization": `Bearer ${key.trim()}`,
      "Content-Type": "application/json"
    }),
    formatBody: (model, systemPrompt, userPrompt) => ({
      model: model,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt }
      ],
      max_tokens: 8192,
      temperature: 0.0,
      top_p: 1.0,
      presence_penalty: 0.0,
      frequency_penalty: 0.0,
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
    parseResponse: (json) => parseJsonText(json?.choices?.[0]?.message?.content || "")
  },
  anthropic: {
    endpoint: "https://api.anthropic.com/v1/messages",
    formatHeaders: (key) => ({
      "x-api-key": key.trim(),
      "anthropic-version": "2023-06-01",
      "content-type": "application/json"
    }),
    formatBody: (model, systemPrompt, userPrompt) => ({
      model: model,
      system: systemPrompt,
      messages: [
        { role: "user", content: userPrompt + "\n\nPlease respond ONLY with a valid JSON object matching the requested schema." }
      ],
      max_tokens: 8192,
      temperature: 0.0,
      top_p: 1.0,
    }),
    parseResponse: (json) => parseJsonText(json?.content?.[0]?.text || "")
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
        temperature: 0.0,
        topP: 1.0,
        presencePenalty: 0.0,
        frequencyPenalty: 0.0,
        maxOutputTokens: 8192,
        responseMimeType: "application/json",
      }
    }),
    parseResponse: (json) => parseJsonText(json?.candidates?.[0]?.content?.parts?.[0]?.text || "")
  }
};

let currentKeyIndex = 0;

// ponytail: nemotron-3-ultra-550b with ~15k context + 8k max_tokens routinely
// needs 30-60s. Bump if you switch to an even larger default model.
const LLM_TIMEOUT_MS = 90000;

export async function callLLMProvider(providerName, apiKeys, modelName, systemPrompt, userPrompt) {
  const provider = PROVIDER_CONFIGS[providerName];
  if (!provider) throw new Error("Unsupported provider: " + providerName);

  if (!apiKeys || apiKeys.length === 0) {
    throw new Error("No API key provided. Please enter your API key in the extension popup settings.");
  }

  const MODEL_ALIASES = {
    "deepseek-ai/deepseek-v4-flash-0731": "nvidia/nemotron-3.5-lightning-30b-a3b",
    "deepseek-ai/deepseek-v4-pro-0813": "nvidia/nemotron-3-super-120b-a12b"
  };

  let rawModel = modelName || "nvidia/nemotron-3-super-120b-a12b";
  const effectiveModel = MODEL_ALIASES[rawModel] || rawModel;

  let overloadRetries = 0; // 503/529: wait and retry the SAME model, don't switch

  for (let attempt = 0; attempt < apiKeys.length; attempt++) {
    const key = apiKeys[currentKeyIndex];
    
    let endpoint = provider.endpoint;
    if (providerName === "gemini") {
       endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${effectiveModel}:generateContent?key=${key.trim()}`;
    }

    const headers = provider.formatHeaders(key);
    const body = provider.formatBody(effectiveModel, systemPrompt, userPrompt);

    console.log("[Skipera LLM] Sending prompt:", { model: effectiveModel, systemPrompt, userPrompt, body });

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: headers,
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(LLM_TIMEOUT_MS)
      });

      if (!response.ok) {
        const errText = await response.text();
        console.error(`[Skipera LLM] HTTP ${response.status} from ${endpoint}:`, errText);

        // Backend overloaded -> switching models won't help. Wait and retry the
        // same model up to 3x (3s, 9s, 20s) before falling through.
        if ((response.status === 503 || response.status === 529) && overloadRetries < 3) {
          const wait = [3000, 9000, 20000][overloadRetries++];
          console.warn(`[Skipera LLM] ${response.status} overloaded; retry ${overloadRetries}/3 in ${wait}ms`);
          await new Promise((r) => setTimeout(r, wait));
          attempt--; // don't consume a key slot
          continue;
        }

        if (response.status === 429 || response.status === 401 || response.status === 402) {
            console.warn(`Key ${currentKeyIndex} failed with ${response.status}. Trying next key...`);
            currentKeyIndex = (currentKeyIndex + 1) % apiKeys.length;
            if (attempt === apiKeys.length - 1) {
               throw new Error(`API Error ${response.status}: ${errText}`);
            }
            continue; // try next key
        }

        // Resilient fallback for NVIDIA when a specific model is overloaded (503) or unavailable
        if (providerName === "nvidia" && [400, 403, 404, 500, 502, 503, 504].includes(response.status)) {
          const NVIDIA_FALLBACKS = [
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "nvidia/nemotron-3-super-120b-a12b",
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "meta/llama-3.3-70b-instruct",
            "deepseek-ai/deepseek-v3"
          ];
          
          for (const fallbackModel of NVIDIA_FALLBACKS) {
            if (fallbackModel === effectiveModel) continue;
            console.warn(`[Skipera LLM] Model ${effectiveModel} failed with ${response.status}. Trying fallback: ${fallbackModel}...`);
            try {
              // Add a short delay if 503 (server overloaded)
              if (response.status === 503 || response.status === 504) {
                await new Promise((r) => setTimeout(r, 1200));
              }
              const fallbackBody = provider.formatBody(fallbackModel, systemPrompt, userPrompt);
              const fallbackRes = await fetch(endpoint, {
                method: "POST",
                headers: headers,
                body: JSON.stringify(fallbackBody),
                signal: AbortSignal.timeout(LLM_TIMEOUT_MS)
              });
              if (fallbackRes.ok) {
                const fallbackJson = await fallbackRes.json();
                console.log(`[Skipera LLM] Fallback model ${fallbackModel} succeeded.`);
                return provider.parseResponse(fallbackJson);
              } else {
                console.warn(`[Skipera LLM] Fallback ${fallbackModel} also failed: ${fallbackRes.status}`);
              }
            } catch (fallbackErr) {
              console.error(`[Skipera LLM] Fallback ${fallbackModel} error:`, fallbackErr);
            }
          }
        }

        throw new Error(`API Error ${response.status}: ${errText}`);
      }

      const json = await response.json();
      console.log("[Skipera LLM] Received raw response:", json);
      const parsed = provider.parseResponse(json);
      console.log("[Skipera LLM] Parsed response:", parsed);
      return parsed;

    } catch (e) {
      if (attempt === apiKeys.length - 1) throw e;
      currentKeyIndex = (currentKeyIndex + 1) % apiKeys.length;
    }
  }
}
