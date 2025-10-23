from __future__ import annotations

import contextlib
import io
from io import StringIO
from typing import Any

from ase.data import atomic_masses
from ase.io import write
from ase import Atoms

# threshold for detecting isotopic masses (amu)
MASS_TOLERANCE = 0.1


def _require_openbabel():
    try:
        from openbabel import openbabel  # lazy import
        return openbabel
    except Exception:
        raise ImportError(
            "Missing optional dependency 'openbabel'. "
            "Install it to enable XYZ/Atoms → InChIKey conversion."
        )

def convert_xyz_to_inchikey(
    xyz_content: str,
    isotopes: dict[int, int] | None = None
) -> str:
    """Convert XYZ file content to an (optionally isotopic) InChIKey using OpenBabel."""
    ob = _require_openbabel()
    ob_conversion = ob.OBConversion()
    ob_mol = ob.OBMol()

    # xyz → inchi
    if not ob_conversion.SetInAndOutFormats("xyz", "inchi"):
        raise ValueError("Failed to set formats for xyz to inchi.")
    if not ob_conversion.ReadString(ob_mol, xyz_content):
        raise ValueError("Failed to parse XYZ content with OpenBabel.")

    # flag isotopes if provided
    if isotopes:
        for atom_idx, mass_number in isotopes.items():
            ob_atom = ob_mol.GetAtom(atom_idx)
            ob_atom.SetIsotope(mass_number)

    # inchi → inchikey
    if not ob_conversion.SetInAndOutFormats("inchi", "inchikey"):
        raise ValueError("Failed to set formats for inchi to inchikey.")

    # suppress OpenBabel stderr output
    with contextlib.redirect_stderr(io.StringIO()):
        inchikey = ob_conversion.WriteString(ob_mol).strip()
    return inchikey


def atoms_to_inchikey(
    atoms: Atoms
) -> str:
    """
    Convert an ASE Atoms object to an InChIKey, automatically detecting
    and tagging any isotopic atoms so the resulting InChIKey includes
    isotopic information.
    """
    masses = atoms.get_masses()
    numbers = atoms.get_atomic_numbers()
    isotopes: dict[int, int] = {}
    for i, (Z, mass) in enumerate(zip(numbers, masses)):
        std_mass = atomic_masses[Z]
        if abs(mass - std_mass) > MASS_TOLERANCE:
            isotopes[i + 1] = int(round(mass))

    # write to XYZ format
    buf = StringIO()
    write(buf, atoms, format="xyz")
    xyz_content = buf.getvalue()
    # convert, passing isotope flags if any
    return convert_xyz_to_inchikey(xyz_content, isotopes=isotopes or None)

def convert_to_inchikey(
    identifier: str,
    id_type: str
) -> str:
    """
    Convert a non-XYZ identifier (SMILES, InChI, etc.) to InChIKey.
    Isotopic information must be encoded in the identifier itself for
    OpenBabel to pick up.
    """
    ob = _require_openbabel()
    conv = ob.OBConversion()
    mol = ob.OBMol()
    fmt_in = {"smiles": "smi"}.get(id_type.lower(), id_type.lower())

    if not conv.SetInAndOutFormats(fmt_in, "inchikey"):
        raise ValueError(f"Cannot convert from '{id_type}' to InChIKey")

    if not conv.ReadString(mol, identifier):
        raise ValueError(f"Failed to parse {id_type!r}: {identifier!r}")

    return conv.WriteString(mol).strip()

def coerce_numeric_fields(record: dict[str, Any], numeric_fields: set[str]) -> dict[str, Any]:
    """Convert fields in record to floats/ints where appropriate."""
    out = {}
    for k, v in record.items():
        if k in numeric_fields and v is not None:
            try:
                if isinstance(v, (int, float)):
                    out[k] = v
                else:
                    # try int first, then float
                    f = float(str(v).strip())
                    out[k] = int(f) if f.is_integer() else f
            except Exception:
                out[k] = None  # drop invalid values
        else:
            out[k] = v
    return out
