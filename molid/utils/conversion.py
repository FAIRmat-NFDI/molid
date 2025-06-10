from ase.io import write
from ase.data import atomic_masses
import io
import contextlib
from io import StringIO
from openbabel import openbabel

# threshold for detecting isotopic masses (amu)
MASS_TOLERANCE = 0.1


def convert_xyz_to_inchikey(xyz_content, isotopes=None):
    """Convert XYZ file content to an (optionally isotopic) InChIKey using OpenBabel."""
    ob_conversion = openbabel.OBConversion()
    ob_mol = openbabel.OBMol()

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


def atoms_to_inchikey(atoms):
    """
    Convert an ASE Atoms object to an InChIKey, automatically detecting
    and tagging any isotopic atoms so the resulting InChIKey includes
    isotopic information.
    """
    # detect isotopes by comparing to standard atomic masses
    masses = atoms.get_masses()
    numbers = atoms.get_atomic_numbers()
    isotopes = {}
    for i, (Z, mass) in enumerate(zip(numbers, masses)):
        std_mass = atomic_masses[Z]
        if abs(mass - std_mass) > MASS_TOLERANCE:
            # round to nearest integer for mass number
            mass_number = int(round(mass))
            # OpenBabel expects 1-based atom indices
            isotopes[i + 1] = mass_number

    # write to XYZ format
    buf = StringIO()
    write(buf, atoms, format="xyz")
    xyz_content = buf.getvalue()

    # convert, passing isotope flags if any
    return convert_xyz_to_inchikey(xyz_content, isotopes=isotopes if isotopes else None)


def convert_to_inchikey(identifier: str, id_type: str) -> str:
    """
    Convert a non-XYZ identifier (SMILES, InChI, etc.) to InChIKey.
    Isotopic information must be encoded in the identifier itself for OpenBabel to pick up.
    """
    conv = openbabel.OBConversion()
    mol = openbabel.OBMol()
    if not conv.SetInAndOutFormats(id_type, "inchikey"):
        raise ValueError(f"Cannot convert from {id_type} to InChIKey")
    if not conv.ReadString(mol, identifier):
        raise ValueError(f"Failed to parse {id_type!r}: {identifier!r}")
    return conv.WriteString(mol).strip()
