from finlint.rules.score import risk_score
from finlint.rules.model import Finding

def test_risk_score_empty_findings():
    assert risk_score([]) == 0
    
def test_same_list():
    findings = [
        Finding(rule_id="rule1", severity="high", sheet="Sheet1", coordinate="A1", message="test"),
        Finding(rule_id="rule2", severity="medium", sheet="Sheet1", coordinate="A2", message="test"),
    ]
    before=[f.severity for f in findings]
    score1 = risk_score(findings)
    score2 = risk_score(findings)
    assert score1 == score2
    
    
    risk_score(findings)
    after=[f.severity for f in findings]
    assert before == after

def test_critical_outscores_fifty_lows():
    fifty_lows=[Finding(rule_id="rule1",severity="low",sheet="Sheet1",coordinate="A1",message="test",blast_radius=999) for x in range(50)]
    critical=Finding(rule_id="rule2",severity="critical",sheet="Sheet1",coordinate="A3",message="...")
  
    
    assert risk_score([critical]) > risk_score(fifty_lows)  # critical weight