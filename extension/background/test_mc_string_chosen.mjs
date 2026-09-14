// Run: node extension/background/test_mc_string_chosen.mjs
// Real production bug: nemotron returned "chosen": "opt_1" (a bare string) for a
// MULTIPLE_CHOICE question instead of ["opt_1"]. postProcess only array-coerced
// CHECKBOX/CHECKBOX_REFLECT, so the string skipped the option_id -> original_id
// mapping entirely, and formatPayload's `chosen[0]` took the first CHARACTER of
// the string ("opt_1"[0] === "o") as the submitted answer. Silently wrong, no
// error, no warning -> submitted a garbage answer id and tanked the quiz grade.
import assert from 'node:assert';
import { LogicAgent } from './agents.js';

const domainQuestions = {
  q1: { Options: [{ option_id: 'opt_1', original_id: 'realId123', value: 'Correct answer text' }] }
};

const agent = new LogicAgent();
const { chosen } = agent.postProcess('MULTIPLE_CHOICE', 'opt_1', '', domainQuestions, 'q1');
const payload = agent.formatPayload('q1', 'MULTIPLE_CHOICE', chosen, '');

assert.equal(
  payload.questionResponse.multipleChoiceResponse.chosen,
  'realId123',
  `expected mapped original_id, got ${JSON.stringify(payload.questionResponse.multipleChoiceResponse.chosen)}`
);

console.log('MC bare-string chosen: OK (mapped to real option id, not truncated to one char)');
