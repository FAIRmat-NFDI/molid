import pytest
from molid.utils.identifiers import normalize_query, UnsupportedIdentifierForMode
from molid.utils.formula import canonicalize_formula

def test_normalize_smiles_basic_maps_to_canonical():
    k, v = normalize_query({"SMILES": "C(=O)=O"}, "basic")
    assert k == "canonicalsmiles"
    assert v == "C(=O)=O"

def test_normalize_isomeric_kept_in_advanced():
    k, v = normalize_query({"IsomericSMILES": "C(=O)=O"}, "advanced")
    assert k == "isomericsmiles"

def test_normalize_isomeric_downgraded_in_basic():
    k, v = normalize_query({"IsomericSMILES": "C(=O)=O"}, "basic")
    assert k == "canonicalsmiles"

def test_normalize_molecularformula_validation():
    # accepted; validation/canonicalization happens downstream
    k, v = normalize_query({"molecularformula": " h2  o "}, "advanced")
    assert k == "molecularformula"
    assert v == " h2  o "  # canonicalization happens later

def test_canonicalize_formula_hill_system_and_spacing():
    assert canonicalize_formula("H2 O") == "H2O"          # no C → alphabetical
    assert canonicalize_formula("H12 C6 O6") == "C6H12O6" # C present → C, H, then alpha

def test_unsupported_identifier_for_mode():
    with pytest.raises(UnsupportedIdentifierForMode):
        normalize_query({"notAKey": 1}, "basic")
