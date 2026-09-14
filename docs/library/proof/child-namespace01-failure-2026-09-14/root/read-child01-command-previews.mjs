import fs from 'node:fs';
const file='E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/real-child-namespace01-root-review/COMMAND-EVENTS.json';
const rows=JSON.parse(fs.readFileSync(file)).events;for(const row of rows){const payload=JSON.parse(row.payload_json),s=payload.step_update;console.log(JSON.stringify({event:row.id,step:s}));}
