"""Manual browser QA against the real Waitress server and fictional data only."""
import sys
import tempfile
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import HRStore,seed,password_hash,IST
from serving import serve_workspace
from backup import configure_backup

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='openpeople-team-browser-') as temporary:
        path=Path(temporary)/'private'/'workspace.db'
        store=HRStore(path,port=8011)
        db=store.connect()
        try:
            with db:
                seed(db)
                db.execute('INSERT INTO employees(name,email,title,department,location,start_date,role,password) VALUES(?,?,?,?,?,?,?,?)',('Team HR','team-hr@example.org','HR Administrator','People & Culture','Remote',datetime.now(IST).date().isoformat(),'hr',password_hash('SyntheticTeamPassword123!')))
                db.execute('UPDATE employees SET password=? WHERE id=1',(password_hash('SyntheticTeamPassword123!'),))
                db.execute("INSERT INTO benefit_plans(title,description,monthly_cost_paise) VALUES('Health cover','Optional company health cover',25000)")
                db.execute("INSERT INTO courses(title,description,url) VALUES('Getting started','Read the team handbook','https://example.org/handbook')")
                db.execute("INSERT INTO course_assignments(employee_id,course_id,due_date) VALUES(1,1,'2026-12-31')")
        finally:
            db.close()
        configure_backup(path,Path(temporary)/'cloud-folder','Synthetic recovery passphrase for test only!',60)
        try:
            serve_workspace(path,port=8011)
        except KeyboardInterrupt:
            pass
