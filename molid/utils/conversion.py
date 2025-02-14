from ase import Atoms
from ase.io import write
from io import StringIO
from openbabel import openbabel

def convert_xyz_to_inchikey(xyz_content):
    """Convert XYZ file content to InChIKey using OpenBabel."""
    ob_conversion = openbabel.OBConversion()
    ob_conversion.SetInAndOutFormats("xyz", "inchi")

    ob_mol = openbabel.OBMol()
    if not ob_conversion.ReadString(ob_mol, xyz_content):
        raise ValueError("Failed to parse XYZ content with OpenBabel.")

    # Convert InChI to InChIKey
    ob_conversion.SetInAndOutFormats("inchi", "inchikey")
    inchikey = ob_conversion.WriteString(ob_mol).strip()
    return inchikey

def atoms_to_inchikey(atoms):
    """Convert an ASE Atoms object to an InChIKey using OpenBabel."""
    xyz_buffer = StringIO()
    write(xyz_buffer, atoms, format="xyz")
    xyz_content = xyz_buffer.getvalue()
    return convert_xyz_to_inchikey(xyz_content)