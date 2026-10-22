from pydantic import BaseModel, Field
from finlint.parsing.reader import read_workbook
from finlint.parsing.formula import make_ref
from finlint.graph.build import build_graph
from finlint.rules.engine import run_all
from finlint.rules.model import Finding
from finlint.rules.score import risk_score
from finlint.agents.auditor import review_findings,ReviewedFinding
from finlint.agents.standards import StandardsResult,explain_with_retriever
from finlint.agents.report import write_report

class PipelineResult(BaseModel):
    path:str
    score:int
    findings:list[Finding]=Field(default_factory=list)
    reviewed: list[ReviewedFinding]=Field(default_factory=list)
    standards: dict[str, StandardsResult]=Field(default_factory=dict)
    report:str

def check_file(path,conn=None,complete=None,limit=5, max_explained=5)->PipelineResult:
    
    workbook=read_workbook(path)
    graph=build_graph(workbook)
    findings=run_all(workbook,graph)
    score=risk_score(findings)
    if not complete:
        return PipelineResult(path=path,score=score,findings=findings,report="")

    reviewed=review_findings(workbook,findings,complete)
    standards={}
    by_cell={}
    for item in reviewed[:max_explained]:
        finding=item.finding
        result=explain_with_retriever(conn,finding=finding,complete=complete,limit=limit)
        standards[make_ref(finding.sheet,finding.coordinate)]=result
        by_cell[(finding.sheet,finding.coordinate)]=result
    
    report=write_report(workbook,reviewed,by_cell,complete)
    
    return PipelineResult(path=path,score=score,findings=findings,reviewed=reviewed,standards=standards,report=report)
    