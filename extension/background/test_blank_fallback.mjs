// Run: node extension/background/test_blank_fallback.mjs
// Guards the blank-answer fallback in quizSolver.js: Coursera 400s the WHOLE
// SaveResponses mutation on an empty-string value or a dropped/undefined field,
// so every agent's payload for a "no answer" question must stay valid JSON.
import assert from 'node:assert';
import { getAgentForType } from './agents.js';

function serialized(payload) {
  return JSON.parse(JSON.stringify(payload)); // mirrors what actually goes over the wire
}

// MULTIPLE_CHOICE with a known option -> real chosen id, never undefined
{
  const p = serialized(getAgentForType('MULTIPLE_CHOICE').formatPayload('q1', 'MULTIPLE_CHOICE', ['optA'], 'N/A'));
  assert.equal(p.questionResponse.multipleChoiceResponse.chosen, 'optA');
}

// MULTIPLE_CHOICE with NO option available -> explicit null, key must survive
{
  const p = serialized(getAgentForType('MULTIPLE_CHOICE').formatPayload('q2', 'MULTIPLE_CHOICE', null, 'N/A'));
  assert.ok('chosen' in p.questionResponse.multipleChoiceResponse, 'chosen key must not be dropped');
  assert.equal(p.questionResponse.multipleChoiceResponse.chosen, null);
}

// RICH_TEXT / TEXT_REFLECT / REGEX / NUMERIC / CODE_EXPRESSION: never send ""
const textCases = [
  // Submission_RichTextInput.cml is an object type, so the text lives one level
  // deeper than the other agents' flat fields.
  ['RICH_TEXT', a => a.questionResponse.richTextResponse.richText.cml.cmlValue],
  ['TEXT_REFLECT', a => a.questionResponse.textReflectResponse.answer],
  ['PLAIN_TEXT', a => a.questionResponse.plainTextResponse.plainText],
  ['TEXT_EXACT_MATCH', a => a.questionResponse.textExactMatchResponse.answer],
];
for (const [qType, get] of textCases) {
  const p = serialized(getAgentForType(qType).formatPayload('q', qType, null, 'N/A'));
  assert.notEqual(get(p), '', `${qType} must not submit an empty string`);
}

{
  const p = serialized(getAgentForType('REGEX').formatPayload('q', 'REGEX', null, 'N/A'));
  assert.notEqual(p.questionResponse.regexResponse.answer, '');
}
{
  const p = serialized(getAgentForType('CODE_EXPRESSION').formatPayload('q', 'CODE_EXPRESSION', null, 'N/A'));
  assert.notEqual(p.questionResponse.codeExpressionResponse.answer.code, '');
}

console.log('blank-fallback payloads: OK');
