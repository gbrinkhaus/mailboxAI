import os
import json
from AICore import getPDFContents_zoned

def test_zoned_output_shape():
    workdir = os.path.join(os.getcwd(), 'tmp_test')
    os.makedirs(workdir, exist_ok=True)
    sample = os.path.join(os.getcwd(), 'test data', 'Invoice_ACME_Corp.pdf')
    text, zones = getPDFContents_zoned(sample, workdir)
    assert isinstance(text, str)
    assert isinstance(zones, dict)
    assert 'zones' in zones
    assert 'merged_entities' in zones
