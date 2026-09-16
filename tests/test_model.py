from datetime import time
import pytest

from pydantic import ValidationError
from finlint.parsing.model import Cell,Sheet,Workbook


def build_sample():
    cell1=Cell(sheet="Config",coordinate="B4",number_format="General",data_type="n",cached_value=100)
    cell2=Cell(sheet="BFR",coordinate="A1",formula="=Config!B4",data_type="f",number_format="General")
    
    sheet1=Sheet(name="Config",state="visible",cells={"B4":cell1})
    sheet2=Sheet(name="BFR",state="hidden",cells={"A1":cell2},merged_ranges=["C1:D1"])
    
    wb=Workbook(path="test.xlsx",sheets={"Config":sheet1,"BFR":sheet2},defined_names={"Revenue":"Config!B4"})
    return wb

def test_formula_keeps_equal_sign():
    wb=build_sample()
    assert wb.sheets["BFR"].cells["A1"].formula[0]=="="
    
def test_dict_key_matches_coordinate():
    wb=build_sample()
    for sheet in wb.sheets.values():
        for key,cell in sheet.cells.items():
            assert key==cell.coordinate
            
def test_later_fields_start_empty():
    c=build_sample().sheets["BFR"].cells["A1"]
    assert c.refs==[]
    assert c.calculated_value is None
    
def test_refs_can_be_filled_later():
    c=build_sample().sheets["BFR"].cells["A1"]
    c.refs.append("Config!B4")
    assert c.refs==["Config!B4"]
    
def test_rejects_unknown_state():
    with pytest.raises(ValidationError):
        Sheet(name="X",state="Locked")

def test_accepts_time_value():
    c=Cell(sheet="X",coordinate="A1",number_format="h:mm",cached_value=time(7,35),data_type="n")
    assert c.cached_value==time(7,35)
    
def test_builds():
    w=build_sample()
    assert w.path=="test.xlsx"
    assert len(w.sheets)==2
    assert w.sheets["Config"].cells["B4"].cached_value==100
    assert w.sheets["BFR"].state=="hidden"
    assert w.sheets["BFR"].merged_ranges==["C1:D1"]
    assert w.defined_names["Revenue"]=="Config!B4"