import { callLLMProvider } from "./llmProviders.js";

async function test() {
  try {
    const keys = ["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"];
    const sysPrompt = "Answer in JSON.";
    const userPrompt = "What is 2+2?";
    const res = await callLLMProvider("nvidia", keys, "nvidia/nemotron-3-ultra-550b-a55b", sysPrompt, userPrompt);
    console.log("Success:", res);
  } catch (e) {
    console.error("Error:", e);
  }
}
test();
