import gzip

import pytest

from molid.pubchemproc.file_handler import (
    GzipValidationError,
    compute_md5,
    read_expected_md5,
    unpack_gz_file,
    validate_gz_file,
    verify_md5,
)


def test_validate_and_unpack_gz_roundtrip(tmp_path):
    # create gz
    payload = b"hello world\n"
    gz = tmp_path / "x.txt.gz"
    with gzip.open(gz, "wb") as f:
        f.write(payload)

    # validate OK
    validate_gz_file(gz)

    # unpack OK
    out = unpack_gz_file(gz, tmp_path)
    assert out.read_bytes() == payload


def test_validate_gz_raises_on_corrupt(tmp_path):
    gz = tmp_path / "broken.gz"
    gz.write_bytes(b"not-a-real-gzip")
    with pytest.raises(GzipValidationError):
        validate_gz_file(gz)


def test_md5_helpers(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"abc123")
    h = compute_md5(f)
    assert len(h) == 32

    md5file = tmp_path / "data.bin.md5"
    md5file.write_text(f"{h}  {f.name}\n")
    assert read_expected_md5(md5file) == h
    assert verify_md5(f, md5file) is True

    md5file.write_text("00000000000000000000000000000000  data.bin\n")
    assert verify_md5(f, md5file) is False
