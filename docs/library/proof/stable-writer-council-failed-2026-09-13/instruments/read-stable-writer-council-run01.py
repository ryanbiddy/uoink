import json
import os
import sqlite3
import sys
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
db = sqlite3.connect('file:C:/Users/hello/AppData/Local/AgentControlRoom/control-room.sqlite?mode=ro', uri=True)
db.row_factory = sqlite3.Row
rows = list(db.execute('SELECT * FROM runs ORDER BY rowid DESC LIMIT 1'))
for row in rows:
    data = dict(row)
    print(json.dumps({'run': {k: v for k, v in data.items() if k in ('id', 'project_id', 'goal', 'status', 'created_at', 'completed_at', 'worktree_path')}}))
    agents = list(db.execute('SELECT * FROM agent_runs WHERE run_id = ?', (data['id'],)))
    for agent in agents:
        print(json.dumps({'agent_columns': list(agent.keys()), 'agent': {k: v for k, v in dict(agent).items() if k in ('id', 'run_id', 'agent', 'engine', 'status', 'worktree_path', 'output_path', 'exit_code', 'model')}}))
db.close()
