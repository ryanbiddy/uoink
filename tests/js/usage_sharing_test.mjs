import assert from 'node:assert/strict';
import { setup } from './rehaul_settings_test.mjs';

const p = setup();
const payload = { schema: 1, tools: { search_library: 2 }, searches: 2 };
const sent = [{ date: '2026-10-21T00:00:00Z', payload }];
p.c.hydrateSettings({ settings: { usage_sharing: false, usage_sharing_forced_off: true,
  usage_sharing_disclosure: { next_payload: payload, sent } } }, {});
assert.equal(p.nodes.get('usageSharing').checked, false);
assert.equal(p.nodes.get('usageSharing').disabled, true);
assert.match(p.nodes.get('usageSharingOverride').textContent, /UOINK_USAGE_SHARING=0/);
assert.deepEqual(JSON.parse(p.nodes.get('usageNextPayload').textContent), payload);
assert.deepEqual(JSON.parse(p.nodes.get('usageSentPayloads').textContent), sent);
assert.match(p.nodes.get('usagePayloadLabel').textContent, /Next payload/);
p.c.renderUsageSettings({ usage_sharing: false,
  usage_sharing_disclosure: { next_payload: payload, sample: true, sent: [] } });
assert.match(p.nodes.get('usagePayloadLabel').textContent, /Sample payload.*Sharing is off.*placeholders/);

p.setHandler(async (path, options) => ({ ok: true, settings: {
  usage_sharing: JSON.parse(options.body).usage_sharing, usage_sharing_forced_off: false,
  usage_sharing_disclosure: { next_payload: payload, sent },
} }));
await p.c.chooseUsageSharing(false);
assert.deepEqual(p.writes.at(-1).body, { usage_sharing: false });
assert.equal(p.nodes.get('usageOptInCard').classList.contains('hidden'), true);
await p.c.chooseUsageSharing(true);
assert.deepEqual(p.writes.at(-1).body, { usage_sharing: true });
assert.equal(p.nodes.get('usageSharing').checked, true);
assert.equal(p.nodes.get('usageSharing').disabled, false);

p.nodes.get('usageSharing').checked = false;
await p.c.saveSettingControl('usageSharing');
assert.deepEqual(p.writes.at(-1).body, { usage_sharing: false });
assert.equal(p.status('usageSharing'), 'Saved');

p.setHandler(async () => ({ ok: true, show: false }));
await p.c.showUsagePrompt();
assert.equal(p.writes.at(-1).path, '/settings/usage-prompt');
assert.equal(p.nodes.get('usageOptInCard').classList.contains('hidden'), true);
p.setHandler(async () => { throw new Error('offline'); });
await p.c.refreshUsageDisclosure();
assert.match(p.nodes.get('usageDisclosureStatus').textContent, /Could not load/);
console.log('PASS usage sharing controls, disclosure, choices and errors');
