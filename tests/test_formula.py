import pytest

from finlint.parsing.formula import make_ref,parse_ref,extract_refs

def test_make_ref():
    assert make_ref("BFR","B12")=="BFR!B12"
    assert make_ref("TVS","BFZ1")=="TVS!BFZ1"
    
@pytest.mark.parametrize(
    "ref,expected",[("BFR!B12",("BFR","B12")),("B12",("","B12")),("A!B!C12",("A!B","C12"))],
)
def test_parse_ref(ref,expected):
    assert parse_ref(ref)==expected
    
@pytest.mark.parametrize(
    "formula,sheet,names,expected",
    [("=TVA!AY24","Trésorerie",{},["TVA!AY24"]),
     ("=SUM(BF48:BF59)","BFR",{},["BFR!BF48:BF59"]),
     ("=AV36-AV55+TVA!AV56","BFR",{},["BFR!AV36","BFR!AV55","TVA!AV56"]),
     ("='Charges Variables'!Q11*Config!$C81","TVA",{},["Charges Variables!Q11","Config!C81"]),
     ("=$G16/12","Charges Externes",{},["Charges Externes!G16"]),
     ("=Year(D11)","Debt Details",{},["Debt Details!D11"]),
     ("=IF(A1>0,L11," ")","S",{},["S!A1","S!L11"]),
     ("=A1+A1","S",{},["S!A1"]),
     ("=Config!B$4+Config!B4","S",{},["Config!B4"]),
     ("=COLUMN()","S",{},[]),
     ("=Revenue*1.1","S",{"Revenue":"Config!B4"},["Config!B4"]),
     ("=Unknown*2","S",{},["Unknown"]),
     ("=SUM(A:A)","S",{},["S!A:A"]),
     ("=SUM(3:3)","S",{},["S!3:3"]),
     ("=[Budget.xlsx]Sheet!A1","S",{},["[Budget.xlsx]Sheet!A1"]),
     ("=SUM(DCF)", "S", {"DCF": "'DCF Analysis'!$B$2:$H$24"}, ["DCF Analysis!B2:H24"]),
     ("='MV Debt and Weighted YTM(Rd)'!B4","S",{},["MV Debt and Weighted YTM(Rd)!B4"]),
     (None,"S",{},[])
    ],
    
)
def test_extract_refs(formula,sheet,names,expected):
    assert extract_refs(formula,sheet,names)==expected