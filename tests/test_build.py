import pytest
from finlint.graph.build import expand_range,build_graph
from finlint.parsing.model import Cell,Sheet,Workbook

    
def build_sample():
    cell1=Cell(sheet="S",coordinate="A1",cached_value=10,data_type="n",number_format="General")
    cell2=Cell(sheet="S",coordinate="A2",formula="=A1*2",data_type="f",number_format="General")
    cell3=Cell(sheet="S",coordinate="A3",formula="=A1+A2",data_type="f",number_format="General")
    cell4=Cell(sheet="S",coordinate="A4",formula="=A3*2",data_type="f",number_format="General")
    cell5=Cell(sheet="S",coordinate="A5",cached_value=25,data_type="n",number_format="General")
    
    sheet=Sheet(name="S",state="visible",cells={"A1":cell1,"A2":cell2,"A3":cell3,"A4":cell4,"A5":cell5})
    wb=Workbook(path="test.xlsx",sheets={"S":sheet},defined_names={})
    return wb   

@pytest.mark.parametrize(
    "reference,expected",
    [
        ("S!B1:B3",["S!B1","S!B2","S!B3"]),
        ("S!B12",["S!B12"]),
        ("S!A:A",["S!A:A"]),
        ("S!3:3",["S!3:3"]),
        ("[Budget.xlsx]S!A1",["[Budget.xlsx]S!A1"]),
        ("Unknown",["Unknown"]),
        ("S!A1:Z200",["S!A1:Z200"])
    ],
)
def test_expand_range(reference,expected):
    assert expand_range(reference)==expected
    
def test_large_range_just_under_the_cap():
    assert len(expand_range("S!A1:Z100"))==2600


def test_feeds():
    graph = build_graph(build_sample())
    feeds = graph.feeds
    assert feeds=={"S!A2": {"S!A1"}, "S!A3": {"S!A1", "S!A2"}, "S!A4": {"S!A3"}}

def test_feeds_into():
    graph = build_graph(build_sample())
    feeds_into = graph.feeds_into
    assert feeds_into=={"S!A1": {"S!A2", "S!A3"}, "S!A2": {"S!A3"}, "S!A3": {"S!A4"}}
    
def test_lonely_cell():
    graph = build_graph(build_sample())
    assert "S!A5" not in graph.feeds or "S!A5" not in graph.feeds_into
    
def test_both_directions_agree():
    graph = build_graph(build_sample())
    for node,targets in graph.feeds.items():
        for t in targets:
            assert node in graph.feeds_into[t]
    