# Plan to Evaluate Replacing PyPDF2

## Notes
- User requested evaluation of replacing PyPDF2 in the project (not py2pdf).
- Need to identify where and how PyPDF2 is used.
- PyPDF2 is used via PdfReader for reading PDFs and extracting text (page.extract_text()).
- Migration to pypdf was attempted but reverted; PyPDF2 is still in use.
- Will research alternative PDF libraries (e.g., ReportLab, FPDF, pdfkit).

## Task List
- [x] Identify all usages of PyPDF2 in the codebase
- [x] Document the specific features and methods used from PyPDF2
- [ ] Research alternative libraries that provide equivalent functionality
- [ ] Compare alternatives and assess migration complexity
- [ ] Recommend whether and how to replace PyPDF2
- [ ] Update pip requirements and imports to use pypdf

## Current Goal
Research alternatives and assess migration complexity