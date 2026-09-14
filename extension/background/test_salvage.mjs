// Run: node extension/background/test_salvage.mjs
// Both fixtures are real malformed payloads from nemotron-3-super-120b that
// previously blanked an entire 10-question quiz (17.5% / 22.5% grades).
import assert from 'node:assert';
import { parseJsonText } from './llmProviders.js';

// Corruption 1: duplicated key fragment in object 2.
const dupKey = `{
  "responses": [
    { "question_id": "a1", "reasoning": "ok", "chosen": ["opt_3"], "answer": "" },
    { "question_id": "question_id": "a2", "reasoning": "bad", "chosen": ["opt_3"], "answer": "" },
    { "question_id": "a3", "reasoning": "ok", "chosen": ["opt_2"], "answer": "" }
  ]
}`;

// Corruption 2: stray `"],` line inside object 1.
const strayToken = `{
  "responses": [
    {
      "question_id": "b1",
      "reasoning": "bad",
      "chosen": ["opt_1"],
      "],
      "answer": ""
    },
    { "question_id": "b2", "reasoning": "ok", "chosen": ["opt_3"], "answer": "" },
    { "question_id": "b3", "reasoning": "ok", "chosen": ["opt_2"], "answer": "" }
  ]
}`;

for (const [name, raw, expectedIds] of [
  ['duplicated key', dupKey, ['a1', 'a3']],
  ['stray token', strayToken, ['b2', 'b3']],
]) {
  const parsed = parseJsonText(raw); // must not throw
  const ids = parsed.responses.map(r => r.question_id);
  assert.deepEqual(ids, expectedIds, `${name}: salvaged ${JSON.stringify(ids)}`);
}

// Well-formed JSON still parses normally, untouched.
const good = parseJsonText('{"responses":[{"question_id":"g1","chosen":["opt_1"]}]}');
assert.equal(good.responses.length, 1);
assert.equal(good.responses[0].question_id, 'g1');

// Genuinely unrecoverable input still throws, so the caller can re-ask.
assert.throws(() => parseJsonText('not json at all {{{'));

console.log('salvageResponses: OK (recovers 2/3 from each corrupt batch, was 0/3)');
