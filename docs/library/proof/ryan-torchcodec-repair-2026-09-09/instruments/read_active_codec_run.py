import json,sqlite3
c=sqlite3.connect('file:C:/Users/hello/AppData/Local/AgentControlRoom/control-room.sqlite?mode=ro',uri=True);c.row_factory=sqlite3.Row
for table,sql in [('run',"SELECT id,status,started_at,heartbeat_at,owner_pid FROM runs WHERE id LIKE 'c662e389%'"),('agent',"SELECT agent,phase,status,started_at,finished_at,length(output) as output_length,error FROM agent_runs WHERE run_id LIKE 'c662e389%'")]:
 print(table,json.dumps([dict(x) for x in c.execute(sql)],indent=2))
c.close()
