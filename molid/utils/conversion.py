from ase import Atoms
from ase.io import write
import os
import contextlib
from io import StringIO
from openbabel import openbabel

def convert_xyz_to_inchikey(xyz_content):
    """Convert XYZ file content to InChIKey using OpenBabel."""
    ob_conversion = openbabel.OBConversion()
    ob_mol = openbabel.OBMol()

    # Set formats for reading the XYZ file and writing the InChI.
    if not ob_conversion.SetInAndOutFormats("xyz", "inchi"):
        raise ValueError("Failed to set formats for xyz to inchi.")

    # Read the XYZ content into the molecule.
    if not ob_conversion.ReadString(ob_mol, xyz_content):
        raise ValueError("Failed to parse XYZ content with OpenBabel.")

    # Convert the molecule to InChI.
    inchi = ob_conversion.WriteString(ob_mol).strip()
    print('inchi:', inchi)

    # Change the conversion format for InChI to InChIKey.
    if not ob_conversion.SetInAndOutFormats("inchi", "inchikey"):
        raise ValueError("Failed to set formats for inchi to inchikey.")

    # Convert the InChI to InChIKey.
    inchikey = ob_conversion.WriteString(ob_mol).strip()
    return inchikey

def atoms_to_inchikey(atoms):
    """Convert an ASE Atoms object to an InChIKey using OpenBabel."""
    xyz_buffer = StringIO()
    write(xyz_buffer, atoms, format="xyz")
    xyz_content = xyz_buffer.getvalue()
    return convert_xyz_to_inchikey(xyz_content)