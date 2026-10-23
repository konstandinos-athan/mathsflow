"""Read-only coverage: legacy questions are never counted as reviewed content."""
import json
import argparse
from pathlib import Path
from collections import Counter
from database import ROOT, DEFAULT_PATH, connect
from database.question_content import normalized


def coverage(db):
    units=list(db.execute('SELECT u.id,u.reference,u.title,c.course_key FROM units u JOIN courses c ON c.id=u.course_id ORDER BY c.rowid,u.display_order'))
    result=[];issues=[]
    for unit in units:
        rows=[dict(json.loads(r[0]),version_id=r[1]) for r in db.execute('SELECT v.payload,v.id FROM questions q JOIN current_questions c ON c.question_id=q.id JOIN question_versions v ON v.id=c.version_id WHERE q.unit_id=?',(unit['id'],))]
        reviewed=[q for q in rows if q.get('hint') and q.get('solution') and q.get('objective_ids') and q.get('verification')]
        levels=Counter(q['difficulty'] for q in reviewed)
        objective_ids={oid for q in reviewed for oid in q['objective_ids']}
        expected={r[0] for r in db.execute('SELECT id FROM objectives WHERE unit_id=?',(unit['id'],))}
        complete=all(levels[level]>=2 for level in ['easy','medium','hard']) and objective_ids==expected
        prompts=Counter(normalized(q['question']) for q in rows)
        for q in rows:
            if prompts[normalized(q['question'])]>1:issues.append({'unit_id':unit['id'],'version_id':q['version_id'],'issue':'duplicate_prompt'})
            if any('\\\\'+delimiter in text for text in [q['question'],*q['choices']] for delimiter in '()[]'):
                issues.append({'unit_id':unit['id'],'version_id':q['version_id'],'issue':'doubled_math_delimiter'})
        result.append({**dict(unit),'questions':len(rows),'with_learning_support':len(reviewed),'difficulties':dict(levels),'objective_ids_covered':sorted(objective_ids),'first_pass_complete':complete,'educator_review':'pending'})
    return {'catalog_units':len(units),'units_with_quiz':sum(r['questions']>0 for r in result),'active_questions':sum(r['questions'] for r in result),'with_learning_support':sum(r['with_learning_support'] for r in result),'first_pass_complete_units':sum(r['first_pass_complete'] for r in result),'remaining_units':sum(not r['first_pass_complete'] for r in result),'educator_approved_units':0,'units':result,'legacy_quality_issues':issues}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=DEFAULT_PATH)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    db=connect(args.database)
    try:report=coverage(db)
    finally:db.close()
    if args.output:args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('units','legacy_quality_issues')},ensure_ascii=False))
