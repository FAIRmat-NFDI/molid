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
