import sys
import json
import traceback
from pathlib import Path

# Ensure repo root is on sys.path so imports like `import helperfuncs` work
# when this script is executed from the scripts/ folder.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

OUT = {
    "python_executable": sys.executable,
    "ok": True,
    "checks": []
}

try:
    # Check PyMuPDF (modern import name)
    try:
        import pymupdf as pymupdf
        v = getattr(pymupdf, "__version__", None)
        OUT['checks'].append({"pymupdf": f"import OK, version={v}"})
    except Exception:
        # Fallback to fitz if someone still uses it
        try:
            import fitz
            v = getattr(fitz, "__doc__", "fitz module available")
            OUT['checks'].append({"fitz": f"import OK ({v})"})
        except Exception as e:
            OUT['checks'].append({"pymupdf": f"import FAILED: {e}"})
            OUT['ok'] = False

    # Import core project modules
    try:
        import helperfuncs
        import AICore
        import app
        import dbhandler
        OUT['checks'].append({"project_imports": "helperfuncs, AICore, app, dbhandler imported"})

        # Basic API checks
        OUT['AICore_has_getPDFContents'] = callable(getattr(AICore, 'getPDFContents', None))
        OUT['AICore_has_getPDFOCR'] = callable(getattr(AICore, 'getPDFOCR', None))
        OUT['app_has_dbhandler'] = hasattr(app, 'dbhandler')
        OUT['app_has_initApp'] = callable(globals().get('initApp', None)) if False else hasattr(app, 'initApp')

    except Exception as e:
        OUT['checks'].append({"project_import_error": str(e)})
        OUT['traceback'] = traceback.format_exc()
        OUT['ok'] = False

except Exception as e:
    OUT['checks'].append({"fatal": str(e)})
    OUT['traceback'] = traceback.format_exc()
    OUT['ok'] = False

print(json.dumps(OUT, indent=2))

# exit non-zero on failure so CI can pick it up
# Run a small functional smoke test if core imports succeeded.
if OUT['ok']:
    try:
        import os, shutil, tempfile
        from helperfuncs import split_pdf_by_pages

        # Candidate sample PDFs: look in the repo 'test data' folder.
        candidates_dir = repo_root / 'test data'
        sample = None
        if candidates_dir.exists():
            pdfs = sorted(candidates_dir.glob('*.pdf'))
            # Prefer files with 'marker' in their name so a user-provided marker PDF
            # like 'marker.pdf' or 'invoice_marker.pdf' is picked automatically.
            marker_pdfs = [p for p in pdfs if 'marker' in p.name.lower()]
            if marker_pdfs:
                sample = marker_pdfs[0]
            elif pdfs:
                # If no marker-named PDF, pick the one with the most pages (best for multipage tests)
                try:
                    import pymupdf as fitz
                    max_pages = -1
                    best = None
                    for p in pdfs:
                        try:
                            d = fitz.open(p)
                            pc = d.page_count
                            d.close()
                        except Exception:
                            pc = 0
                        if pc > max_pages:
                            max_pages = pc
                            best = p
                    sample = best if best else pdfs[0]
                except Exception:
                    sample = pdfs[0]

        OUT['functional'] = { 'sample_found': bool(sample) }

        if sample:
            # Prepare temp workdir inside scripts to make outputs inspectable
            tmpdir = repo_root / 'scripts' / 'tmp_smoke'
            tmpdir.mkdir(parents=True, exist_ok=True)

            dest = tmpdir / sample.name
            shutil.copyfile(sample, dest)

            # Extraction test using AICore
            try:
                text = AICore.getPDFContents(str(dest), str(tmpdir))
                OUT['functional']['extracted_text_len'] = len(text) if text is not None else 0
                OUT['functional']['extraction_ok'] = bool(text and len(text) > 10)
            except Exception as e:
                OUT['functional']['extraction_ok'] = False
                OUT['functional']['extraction_error'] = str(e)

            # Marker detection + split test
            try:
                # Ensure app.workdir is set so extract_markers / OCR fallback can run
                try:
                    app.workdir = str(tmpdir)
                except Exception:
                    pass

                markers = []
                try:
                    markers = app.extract_markers(str(dest), str(tmpdir))
                    OUT['functional']['markers'] = markers
                except Exception as e:
                    OUT['functional']['markers_error'] = str(e)

                # Run split (will create files inside tmpdir)
                try:
                    outputs = split_pdf_by_pages(str(tmpdir), dest.name, markers)
                    OUT['functional']['split_outputs'] = outputs
                    OUT['functional']['split_ok'] = outputs > 0
                except Exception as e:
                    OUT['functional']['split_ok'] = False
                    OUT['functional']['split_error'] = str(e)
            except Exception:
                # swallow
                pass

    except Exception as e:
        OUT['functional_error'] = str(e)

    # Print extended output and set exit code accordingly
    print('\nFunctional checks:')
    print(json.dumps(OUT.get('functional', {}), indent=2))

sys.exit(0 if OUT['ok'] else 2)
